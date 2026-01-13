import os
import shutil
import math
import traceback
import json
import re
import uuid
import glob
from datetime import datetime

import duckdb
import polars as pl
from fastapi import FastAPI, UploadFile, File, BackgroundTasks, Query, Request, HTTPException
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse

# /root
#   /.config/recommendation.json
#   /desa_db/server.py
#   /desa_db/middleware.py
#   /front_end/web.py
#   /front_end/templates/admin.html
#   /front_end/templates/login.html

# ==========================================
# Configuration & Constants
# ==========================================
# Import the optimized middleware
try:
    from middleware import apply_recommendations
except ImportError:
    # Fallback if running from a different context
    from desa_db.middleware import apply_recommendations

app = FastAPI()

# ==========================================
# PATH CONFIGURATION (ABSOLUTE PATHS)
# ==========================================

# Get the directory where server.py is located (e.g., C:/.../desa_db)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# DB Folder: inside desa_db/dbs
DB_FOLDER = os.path.join(BASE_DIR, "dbs")

# Temp folder for uploads
STAGING_FOLDER = os.path.join(BASE_DIR, "staging")

# Header File: inside .config/headers.txt (sibling of desa_db)
# Go up one level (..) to root, then into .config
CONFIG_DIR = os.path.abspath(os.path.join(BASE_DIR, "../.config"))
HEADER_FILE = os.path.join(CONFIG_DIR, "headers.txt")

# Data Structure Constants
# ID_COL acts as the Primary Key for deduplication and version control.
ID_COL = "Kode Wilayah Administrasi Desa" 

# Ensure directories exist
os.makedirs(DB_FOLDER, exist_ok=True)
os.makedirs(STAGING_FOLDER, exist_ok=True)
os.makedirs(CONFIG_DIR, exist_ok=True)

# ==========================================
# HELPERS
# ==========================================
def get_db_connection(year: str):
    """
    Establishes a connection to a specific year's DuckDB database.
    DuckDB runs in-process, saving data to a local file.
    """
    get_db_connection_clean_year = os.path.basename(year) # Security: Prevent ".." path traversal
    db_path = os.path.join(DB_FOLDER, f"data_{get_db_connection_clean_year}.duckdb")
    con = duckdb.connect(db_path)
    return con, db_path

def get_cache_path(year: str):
    """Returns the absolute path for the cache file for a specific year."""
    get_cache_path_clean_year = os.path.basename(year)
    return os.path.join(CONFIG_DIR, f"unique_cache_{get_cache_path_clean_year}.json")

def init_db(con: duckdb.DuckDBPyConnection, headers: list[str]):
    """
    SCD Type 2 Schema:
    
    Architecture:
    - valid_from: Timestamp when this row became active.
    - valid_to: Timestamp when this row was replaced/deleted (NULL = Currently Active).
    - commit_id: Groups changes by upload transaction.
    """
    # Construct column definitions for SQL (e.g., "Col1" VARCHAR, "Col2" VARCHAR...)
    # Note: Wrap headers in double quotes to handle spaces or special chars in column names.
    cols_def = ", ".join([f'"{h}" VARCHAR' for h in headers])
    
    # Create the MAIN table (Latest Snapshot)
    # Includes metadata: 'last_updated' and 'source_file'
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS master_data (
            valid_from TIMESTAMP,
            valid_to TIMESTAMP,
            commit_id VARCHAR,
            source_file VARCHAR,
            {cols_def}
        )
    """)

    # Index for speed
    con.execute(f"CREATE INDEX IF NOT EXISTS idx_id ON master_data (\"{ID_COL}\")")
    
    # Create the HISTORY table (Audit Log)
    # Identical structure but includes 'archived_at' to track when the record was replaced.
    con.execute("""
        CREATE TABLE IF NOT EXISTS commits (
            commit_id VARCHAR PRIMARY KEY,
            timestamp TIMESTAMP,
            filename VARCHAR,
            summary VARCHAR
        )
    """)

def refresh_filter_cache(year: str):
    """
    Builds a hierarchical JSON tree:
    {
        "Provinsi A": {
            "Kabupaten A1": ["Kecamatan A1-1", "Kecamatan A1-2"],
            "Kabupaten A2": [...]
        },
        ...
    }
    """
    con, _ = get_db_connection(year)
    hierarchy = {}

    # Columns to cache for dropdowns
    # You can add more here if needed
    target_columns = ["Provinsi", "Kabupaten/ Kota", "Kecamatan"]
    
    try:
        # Check if table exists
        tables = con.execute("SHOW TABLES").fetchall()
        if not tables or ('master_data',) not in tables:
            return

        # Fetch all unique combinations in one go (Very Fast)
        # Assume headers are standard. Adjust exact column names if needed.
        query = """
            SELECT DISTINCT "Provinsi", "Kabupaten/ Kota", "Kecamatan" 
            FROM master_data
            WHERE valid_to IS NULL AND "Provinsi" IS NOT NULL
            ORDER BY "Provinsi", "Kabupaten/ Kota", "Kecamatan"
        """
        rows = con.execute(query).fetchall()
        
        # Build the Tree
        for prov, kab, kec in rows:
            if prov not in hierarchy:
                hierarchy[prov] = {}
            if kab not in hierarchy[prov]:
                hierarchy[prov][kab] = []
            if kec not in hierarchy[prov][kab]:
                hierarchy[prov][kab].append(kec)
        
        # Write to disk
        with open(get_cache_path(year), "w", encoding="utf-8") as f:
            json.dump(hierarchy, f, ensure_ascii=False)
            
        print(f"✅ Hierarchy Cache refreshed: {cache_path}")
        
    except Exception as e:
        print(f"❌ Error refreshing hierarchy: {e}")
    finally:
        con.close()

def build_dynamic_query(con, base_query, request_params):
    """
    Dynamically adds WHERE or AND clauses based on URL parameters.
    Ignores system params like 'limit', 'translate', 'year'.
    """
    # Get valid column names from the 'master_data' table to prevent SQL injection
    valid_cols = [r[0] for r in con.execute("DESCRIBE master_data").fetchall()]
    
    filters = []
    values = []
    
    # Iterate over all query parameters
    # A. SPECIAL FILTER: ID List (Comma Separated)
    if "ids" in request_params and request_params["ids"]:
        raw_ids = request_params["ids"]

        # Split by comma, newline, or carriage return
        filtered_ids = re.split(r'[,\n\r]+', raw_ids)

        # Strip each token and remove empty strings in one pass
        id_list = [x.strip() for x in filtered_ids if x.strip()]

        if id_list:
            # Create placeholders (?, ?, ?)
            placeholders = ", ".join(["?"] * len(id_list))
            filters.append(f'"{ID_COL}" IN ({placeholders})')
            values.extend(id_list)

    # B. STANDARD FILTERS
    ignored_keys = ["ids", "version", "limit", "translate", "staging_id", "filename"]
    for key, val in request_params.items():
        # Map URL friendly names if necessary, or use direct keys
        # Assume frontend sends specific column names like "Provinsi"
        if key in valid_cols and key not in ignored_keys and val:
            filters.append(f'"{key}" ILIKE ?')
            values.append(f"%{val}%")
            
    # Smart Append
    if filters:
        filter_str = " AND ".join(filters)
        # Check if base_query already has a WHERE clause (case-insensitive)
        if "WHERE" in base_query.upper():
            base_query += f" AND {filter_str}"
        else:
            base_query += f" WHERE {filter_str}"
        
    return base_query, values

# ==========================================
# API Endpoints
# ==========================================

# STAGE: Upload -> Analyze Diff -> Return Stats
@app.post("/stage/{year}")
async def stage_upload(
    year: str,
    file: UploadFile = File(...)
    ):
    """
    Ingests an Excel (.xlsb) file, cleans it, and performs a "Change Data Capture" (CDC) update.
    
    Workflow:
    1. Read Excel via Polars.
    2. clean structural garbage (headers/empty cols).
    3. Compare new data against existing DB data.
    4. Archive changed rows to 'history'.
    5. Upsert (Update/Insert) new rows to 'master_data'.
    """

    # Security: Sanitize filename
    safe_filename = os.path.basename(file.filename)
    staging_id = str(uuid.uuid4())
    temp_path = os.path.join(STAGING_FOLDER, f"{staging_id}.parquet")
 
    try:
        # --- 1. File I/O ---
        # Preserve extension so Calamine knows if it's xlsx or xlsb
        _, ext = os.path.splitext(safe_filename)
        if not ext: ext = ".xlsb"
        temp_upload_file = f"temp_upload_{staging_id}{ext}"

        with open(temp_upload_file, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # --- 2. Load Schema Definition ---
        # Ideally, load this from a config file.
        if not os.path.exists(HEADER_FILE):
             return JSONResponse(
                 status_code=500,
                 content={
                     "error": f"Configuration file not found: {HEADER_FILE}"
                     }
                 )

        with open(HEADER_FILE, "r", encoding="utf-8") as f:
            stage_upload_header = [line.strip() for line in f if line.strip()]

        # --- 3. ETL: Extraction & Cleaning (Polars) ---
        print(f"Processing {file.filename} for year {year}...")
        
        # Read .xlsb using 'calamine' (fastest engine for binary excel)
        df = pl.read_excel(
            temp_upload_file,
            sheet_name="Skor",
            engine="calamine",
        )
        
        # Structure Cleaning:
        # Slice: Skip the first 4 rows (assumed to be report titles/metadata)
        df = df.slice(3, None)
        
        # Slice: Cap width to prevent reading infinite empty Excel columns
        max_col = min(df.width, 262) 
        # Also skip the very first index column (0)
        df = df[:, 1:max_col]

        # Filter: Remove columns that are entirely Empty or Null
        df = df.select([
            col for col in df 
            if not (col.is_null().all() or (col.dtype == pl.String and (col == "").all()))
        ])
        
        # Filter: Keep only rows where at least one column looks like an ID
        # Pattern: 10 digits (Standard Indonesian Region Code)
        pattern = r"[0-9]{10}"
        df = df.filter(
            pl.any_horizontal(
                pl.all().cast(pl.String).str.contains(pattern)
            )
        )

        # Schema: Apply standard headers from headers.txt
        limit = min(len(df.columns), len(stage_upload_header))
        df = df[:, :limit]
        df.columns = stage_upload_header[:limit]

        # Save Staged Data
        df.write_parquet(temp_path)

        # --- 4. Database Merge Logic (DuckDB) ---
        con, db_path = get_db_connection(year)
        init_db(con, df.columns)
        
        # Identify Incoming Data
        con.execute(f"CREATE OR REPLACE TEMP TABLE incoming AS SELECT * FROM read_parquet('{temp_path}')")

        # Current Active State
        con.execute("CREATE OR REPLACE TEMP TABLE current_state AS SELECT * FROM master_data WHERE valid_to IS NULL")
        
        # Rows to ADD (ID in Incoming, Not in Current)
        added_count = con.execute(f"""
            SELECT COUNT(*) FROM incoming i 
            WHERE i."{ID_COL}" NOT IN (SELECT "{ID_COL}" FROM current_state)
        """).fetchone()[0]
        
        # Rows to REMOVE (ID in Current, Not in Incoming) - FULL SYNC OPTION
        removed_count = con.execute(f"""
            SELECT COUNT(*) FROM current_state c
            WHERE c."{ID_COL}" NOT IN (SELECT "{ID_COL}" FROM incoming)
        """).fetchone()[0]

        # Rows to UPDATE (ID Match, Content Differs)
        other_cols = [h for h in df.columns if h != ID_COL]
        # Handle single column case or empty other_cols
        if not other_cols:
            changed_count = 0
        else:
            check_conditions = " OR ".join([f'(c."{h}" IS DISTINCT FROM i."{h}")' for h in other_cols])
            changed_count = con.execute(f"""
                SELECT COUNT(*) FROM current_state c
                JOIN incoming i ON c."{ID_COL}" = i."{ID_COL}"
                WHERE {check_conditions}
            """).fetchone()[0]
            
        con.close()
        
        return {
            "status": "staged",
            "staging_id": staging_id,
            "filename": safe_filename,
            "diff": {
                "added": added_count,
                "removed": removed_count,
                "changed": changed_count,
                "total_incoming": df.height
            }
        }

    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        if os.path.exists(temp_upload_file): 
            os.remove(temp_upload_file)

# COMMIT: Apply the Staged Changes
@app.post("/commit/{year}")
async def commit_stage(
    year: str,
    staging_id: str = Query(...),
    filename: str = Query(...)
    ):
    """
    Commits staged upload to SCD Type 2 master_data table.

    Performs:
    - Expire removed records (IDs missing in new data)
    - Expire changed records (same ID, different values in any non-key column)
    - Insert new & updated versions (valid_from=now, valid_to=NULL)

    Uses single transaction + IS DISTINCT FROM for change detection.
    Cleans up staging file on success.
    """
    temp_path = os.path.join(STAGING_FOLDER, f"{staging_id}.parquet")
    if not os.path.exists(temp_path):
        return JSONResponse(status_code=404, content={"error": "Staging session expired. Please upload again."})
        
    con, _ = get_db_connection(year)
    try:
        con.execute("BEGIN TRANSACTION")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        con.execute(f"CREATE OR REPLACE TEMP TABLE incoming AS SELECT * FROM read_parquet('{temp_path}')")
        
        # 1. Close REMOVED rows (Set valid_to = now)
        con.execute(f"""
            UPDATE master_data SET valid_to = '{now}'
            WHERE valid_to IS NULL 
            AND "{ID_COL}" NOT IN (SELECT "{ID_COL}" FROM incoming)
        """)
        
        # 2. Close UPDATED rows (Set valid_to = now)
        # detect changes via IS DISTINCT FROM for all non-ID columns
        valid_cols = [r[0] for r in con.execute("DESCRIBE incoming").fetchall()]
        other_cols = [h for h in valid_cols if h != ID_COL]
        
        if other_cols:
            # Changed 'm' to 'master_data' to match the table name in the UPDATE statement
            check_cond = " OR ".join([f'(master_data."{h}" IS DISTINCT FROM i."{h}")' for h in other_cols])
            
            con.execute(f"""
                UPDATE master_data SET valid_to = '{now}'
                FROM incoming i
                WHERE master_data."{ID_COL}" = i."{ID_COL}"
                AND master_data.valid_to IS NULL
                AND ({check_cond})
            """)
        
        # 3. Insert NEW and UPDATED versions (Set valid_from = now, valid_to = NULL)
        # Insert New IDs
        con.execute(f"""
            INSERT INTO master_data 
            SELECT '{now}', NULL, '{staging_id}', '{filename}', i.* FROM incoming i
            WHERE i."{ID_COL}" NOT IN (
                SELECT "{ID_COL}" FROM master_data WHERE valid_to IS NULL
            )
        """)
        
        # Log Commit
        summary = "Update"
        con.execute(f"INSERT INTO commits VALUES ('{staging_id}', '{now}', '{filename}', '{summary}')")
        
        con.execute("COMMIT")
        refresh_filter_cache(year)
        
        return {"status": "success", "message": "Database updated successfully."}
        
    except Exception as e:
        con.execute("ROLLBACK")
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        con.close()
        if os.path.exists(temp_path): os.remove(temp_path)

# QUERY: Supports Time Travel via 'version' (Timestamp)
@app.get("/query/{year}")
def query_data(
    year: str,
    request: Request,
    limit: int = 500,
    filter_col: str = None,
    filter_val: str = None,
    translate: bool = False,
    version: str = None
    ):
    """
    'last_updated' is automatically the first column (Left Most).
    Retrieves the latest data snapshot from the 'master_data' table.
    Includes basic string filtering and JSON NaN sanitization.
    """
    con, _ = get_db_connection(year)
    try:
        # Ensure database is initialized before querying
        try:
            con.execute("SELECT 1 FROM master_data")
        except:
            return JSONResponse(status_code=404, content={"error": "Table not found."})

        # --- TIME TRAVEL LOGIC ---
        # If version is provided (Timestamp), look for rows active AT that time.
        # If version is NULL, look for rows currently active (valid_to IS NULL).
        if version:
            # Snapshot Mode: Active at time T
            time_filter = f"valid_from <= '{version}' AND (valid_to > '{version}' OR valid_to IS NULL)"
        else:
            # HEAD Mode
            time_filter = "valid_to IS NULL"

        base_query = f"SELECT * EXCLUDE (valid_from, valid_to, commit_id) FROM master_data WHERE {time_filter}"
        
        # Dynamic Filters
        params_dict = dict(request.query_params)
        final_query, values = build_dynamic_query(con, base_query, params_dict)
        
        final_query += f" LIMIT {limit}"
        
        res = con.execute(final_query, values).pl()
        if translate: res = apply_recommendations(res)
        
        # Sanitize NaNs
        records = res.to_dicts()
        clean = [{k: (None if isinstance(v, float) and math.isnan(v) else v) for k,v in r.items()} for r in records]
        
        return JSONResponse(clean)
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        con.close()

# DOWNLOAD
@app.get("/download/{year}")
def download(
    year: str,
    background_tasks: BackgroundTasks,
    request: Request,
    translate: bool = False,
    version: str = None
    ):
    """
    Export Endpoint:
    1. Reads DuckDB.
    2. Writes to temporary Excel.
    3. Returns file to user.
    4. Deletes temporary file after response is sent.
    """
    con, db_path = get_db_connection(year)
    temp_download = f"export_{year}.xlsx"
    
    try:
        if version:
            time_filter = f"valid_from <= '{version}' AND (valid_to > '{version}' OR valid_to IS NULL)"
        else:
            time_filter = "valid_to IS NULL"
        # Build Query with SAME filters as View
        base_query = f"SELECT * EXCLUDE (valid_from, valid_to, commit_id) FROM master_data WHERE {time_filter}"

        # Use Helper
        params_dict = dict(request.query_params)
        final_query, values = build_dynamic_query(con, base_query, params_dict)
        
        df = con.execute(final_query, values).pl()
        if translate: df = apply_recommendations(df)

        # Write Excel
        df.write_excel(temp_download)

        # Schedule deletion
        background_tasks.add_task(os.remove, temp_download)

        return FileResponse(
            temp_download,
            filename=f"Data_{year}_{version or 'HEAD'}.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        traceback.print_exc()
        if os.path.exists(temp_download):
            os.remove(temp_download)
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        con.close()

# VERSIONS LIST
@app.get("/history/versions/{year}")
def get_history_versions(year: str):
    """
    Returns list of source files (versions) uploaded
    """
    con, _ = get_db_connection(year)
    try:
        # Return distinct timestamps from the commits table
        # Format: "2025-01-13 17:00:00"
        commit_timestamp = con.execute("SELECT timestamp, filename FROM commits ORDER BY timestamp DESC").fetchall()
        # Return list of {timestamp, label}
        return [{"ts": str(r[0]), "label": f"{r[0]} - {r[1]}"} for r in commit_timestamp]
    except:
        return []
    finally:
        con.close()

# HIERARCHY
@app.get("/hierarchy/{year}") 
def get_filter_hierarchy(year: str):
    """
    Returns the full location tree (Prov -> Kab -> Kec)
    """
    cache_path = get_cache_path(year)
    if os.path.exists(cache_path):
        return FileResponse(cache_path, media_type="application/json")
    return {}
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
