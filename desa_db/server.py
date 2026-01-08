import os
import shutil
import math
import traceback
import json

import duckdb
import polars as pl
from fastapi import FastAPI, UploadFile, File, BackgroundTasks, Query, Request, HTTPException
from fastapi.responses import JSONResponse, FileResponse

# /root
#   /.config/recommendation.json
#   /desa_db/server.py
#   /desa_db/middleware.py

# ==========================================
# Application Configuration & Constants
# ==========================================
# Import the optimized middleware
from middleware import apply_recommendations

app = FastAPI()

# ==========================================
# PATH CONFIGURATION (ABSOLUTE PATHS)
# ==========================================

# Get the directory where server.py is located (e.g., C:/.../desa_db)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# DB Folder: inside desa_db/dbs
DB_FOLDER = os.path.join(BASE_DIR, "dbs")

# Header File: inside .config/headers.txt (sibling of desa_db)
# We go up one level (..) to root, then into .config
CONFIG_DIR = os.path.abspath(os.path.join(BASE_DIR, "../.config"))
HEADER_FILE = os.path.join(CONFIG_DIR, "headers.txt")

# Data Structure Constants
# ID_COL acts as the Primary Key for deduplication and version control.
ID_COL = "Kode Wilayah Administrasi Desa" 

# Ensure directories exist
os.makedirs(DB_FOLDER, exist_ok=True)
os.makedirs(CONFIG_DIR, exist_ok=True)

# ==========================================
# CACHE HELPER FUNCTIONS (NEW)
# ==========================================
def get_cache_path(year: str):
    """Returns the absolute path for the cache file for a specific year."""
    return os.path.join(CONFIG_DIR, f"unique_cache_{year}.json")

def refresh_filter_cache(year: str):
    """
    Runs HEAVY queries (SELECT DISTINCT) once and saves result to JSON.
    This runs only during upload.
    """
    con, _ = get_db_connection(year)
    cache_data = {}
    
    # Columns we want to cache for dropdowns
    # You can add more here if needed
    target_columns = ["Provinsi", "Kabupaten/ Kota", "Kecamatan"]
    
    try:
        # Check if table exists
        tables = con.execute("SHOW TABLES").fetchall()
        if not tables or ('main',) not in tables:
            return
            
        for col in target_columns:
            # Check if column exists in table to avoid crashing
            try:
                # Get unique values, sorted alphabetically
                query = f'SELECT DISTINCT "{col}" FROM main WHERE "{col}" IS NOT NULL ORDER BY "{col}" ASC'
                rows = con.execute(query).fetchall()
                # Convert list of tuples [('Aceh',), ('Bali',)] -> list of strings ['Aceh', 'Bali']
                cache_data[col] = [r[0] for r in rows]
            except:
                print(f"⚠️ Warning: Column '{col}' not found in DB, skipping cache.")
                cache_data[col] = []
        
        # Write to disk
        cache_path = get_cache_path(year)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False)
            
        print(f"✅ Cache refreshed: {cache_path}")
        
    except Exception as e:
        print(f"❌ Error refreshing cache: {e}")
    finally:
        con.close()

# ==========================================
# Database Helper Functions
# ==========================================

def get_db_connection(year: str):
    """
    Establishes a connection to a specific year's DuckDB database.
    DuckDB runs in-process, saving data to a local file.
    """
    db_path = os.path.join(DB_FOLDER, f"data_{year}.duckdb")
    con = duckdb.connect(db_path)
    return con, db_path

def init_db(con: duckdb.DuckDBPyConnection, headers: list[str]):
    """
    Initializes the database schema if it does not already exist.
    
    Architecture:
    1. 'main': The current, active state of the data (Snapshot).
    2. 'history': An append-only audit log containing previous versions of rows.
    
    Args:
        con: Active DuckDB connection.
        headers: List of column names to construct the schema dynamically.
    """
    # Construct column definitions for SQL (e.g., "Col1" VARCHAR, "Col2" VARCHAR...)
    # Note: We wrap headers in double quotes to handle spaces or special chars in column names.
    cols_def = ", ".join([f'"{h}" VARCHAR' for h in headers])
    
    # Create the MAIN table (Latest Snapshot)
    # Includes metadata: 'last_updated' and 'source_file'
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS main (
            last_updated TIMESTAMP,
            source_file VARCHAR,
            {cols_def},
            PRIMARY KEY ("{ID_COL}")
        )
    """)
    
    # Create the HISTORY table (Audit Log)
    # Identical structure but includes 'archived_at' to track when the record was replaced.
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS history (
            archived_at TIMESTAMP,
            last_updated TIMESTAMP,
            source_file VARCHAR,
            {cols_def}
        )
    """)

# --- Dynamic Filter Builder ---
def build_dynamic_query(con, base_query, request_params):
    """
    Dynamically adds WHERE clauses based on URL parameters.
    Ignores system params like 'limit', 'translate', 'year'.
    """
    # Get valid column names from the 'main' table to prevent SQL injection
    valid_cols = [r[0] for r in con.execute("DESCRIBE main").fetchall()]
    
    filters = []
    values = []
    
    # Iterate over all query parameters
    for key, val in request_params.items():
        # Map URL friendly names if necessary, or use direct keys
        # We assume frontend sends specific column names like "Provinsi"
        if key in valid_cols and val:
            filters.append(f'"{key}" ILIKE ?')
            values.append(f"%{val}%")
            
    if filters:
        base_query += " WHERE " + " AND ".join(filters)
        
    return base_query, values

# ==========================================
# API Endpoints
# ==========================================

@app.post("/upload/{year}")
async def upload_xlsb(year: str, file: UploadFile = File(...)):
    """
    Ingests an Excel (.xlsb) file, cleans it, and performs a "Change Data Capture" (CDC) update.
    
    Workflow:
    1. Read Excel via Polars.
    2. clean structural garbage (headers/empty cols).
    3. Compare new data against existing DB data.
    4. Archive changed rows to 'history'.
    5. Upsert (Update/Insert) new rows to 'main'.
    """
    temp_xlsb = f"temp_{file.filename}"
    
    try:
        # --- 1. File I/O ---
        # Save upload to disk temporarily because Polars/Calamine needs a file path
        with open(temp_xlsb, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # --- 2. Load Schema Definition ---
        # Ideally, load this from a config file.
        if not os.path.exists(HEADER_FILE):
             return JSONResponse(status_code=500, content={"error": f"Configuration file not found: {HEADER_FILE}"})
             
        with open(HEADER_FILE, "r", encoding="utf-8") as f:
            manual_headers = [line.strip() for line in f if line.strip()]

        # --- 3. ETL: Extraction & Cleaning (Polars) ---
        print(f"Processing {file.filename} for year {year}...")
        
        # Read .xlsb using 'calamine' (fastest engine for binary excel)
        df = pl.read_excel(
            temp_xlsb, 
            sheet_name="Skor", 
            engine="calamine",
            read_options={"header_row": None} # Read as raw data to handle messy layouts
        )
        
        # Structure Cleaning:
        # 1. Slice: Skip the first 6 rows (assumed to be report titles/metadata)
        df = df.slice(6, None)
        
        # 2. Slice: Cap width to prevent reading infinite empty Excel columns
        max_col = min(df.width, 262) 
        df = df[:, 1:max_col] # Also skip the very first index column (0)

        # 3. Filter: Remove columns that are entirely Empty or Null
        df = df.select([
            col for col in df 
            if not (col.is_null().all() or (col.dtype == pl.String and (col == "").all()))
        ])
        
        # 4. Filter: Keep only rows where at least one column looks like an ID
        #    Pattern: 10 digits (Standard Indonesian Region Code)
        pattern = r"[0-9]{10}"
        df = df.filter(
            pl.any_horizontal(
                pl.all().cast(pl.String).str.contains(pattern)
            )
        )

        # 5. Schema: Apply standard headers from headers.txt
        limit = min(len(df.columns), len(manual_headers))
        df = df[:, :limit]
        df.columns = manual_headers[:limit]


        # --- 4. Database Merge Logic (DuckDB) ---
        con, db_path = get_db_connection(year)
        init_db(con, df.columns)

        # Load Polars DF as a virtual view in DuckDB for SQL querying
        con.register("new_data", df)
        
        # Step A: Identify Incoming Data
        con.execute("CREATE OR REPLACE TEMP TABLE incoming AS SELECT * FROM new_data")

        # Step B: Change Detection
        # Compare 'incoming' vs 'main'. If IDs match but content differs, it's an update.
        # We use IS DISTINCT FROM to handle NULLs correctly.
        other_cols = [h for h in df.columns if h != ID_COL]
        check_conditions = " OR ".join([f'(m."{h}" IS DISTINCT FROM i."{h}")' for h in other_cols])

        # SQL to find specific rows in 'main' that are about to be overwritten
        rows_to_update_sql = f"""
            SELECT m.* FROM main m
            JOIN incoming i ON m."{ID_COL}" = i."{ID_COL}"
            WHERE {check_conditions}
        """
        
        # Step C: Archive Old Data
        # Take the "current" version of rows that are changing and push them to 'history'
        con.execute(f"""
            INSERT INTO history 
            SELECT current_timestamp as archived_at, * FROM ({rows_to_update_sql})
        """)
        
        # Step D: UPSERT (Update + Insert)
        # We replace the main table's rows with the new incoming rows.
        # Filter logic:
        # 1. New IDs (Not in main) -> Insert
        # 2. Existing IDs that have changed -> Update (Replace)
        # Note: Unchanged rows are ignored to preserve original 'last_updated' timestamps.
        con.execute(f"""
            INSERT OR REPLACE INTO main
            SELECT 
                current_timestamp as last_updated,
                '{file.filename}' as source_file,
                i.*
            FROM incoming i
            WHERE 
                i."{ID_COL}" NOT IN (SELECT "{ID_COL}" FROM main) -- Logic for New Inserts
                OR 
                i."{ID_COL}" IN (SELECT "{ID_COL}" FROM ({rows_to_update_sql})) -- Logic for Updates
        """)
        
        con.close()
        
        return {
            "status": "success",
            "year": year,
            "rows_processed": df.height,
            "db_path": db_path
        }

    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        # Cleanup temporary file
        if os.path.exists(temp_xlsb):
            os.remove(temp_xlsb)

@app.get("/unique/{year}") 
def get_unique_values(year: str, column: str = Query(...)):
    """
    Retrieves distinct values for a specified column from the 'main' table.
    Basically this is the endpoint to populate dropdown filters dynamically.
    first tries to read from cache, if cache miss then queries DB directly.
    Cache File: .config/unique_cache_{year}.json
    """
    cache_path = get_cache_path(year)
    
    # 1. Try to read from Cache File
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            # If the column exists in our cache, return it immediately
            if column in data:
                return data[column]
        except Exception as e:
            print(f"Cache read error: {e}")
            # If cache is corrupted, we fall through to the fallback below
            
    # Fallback: If cache missing or column not in cache (e.g. first run)
    # We query the DB directly. This ensures the app never breaks even if cache is gone.
    print(f"Cache miss for {column}. Querying DB...")

    con, _ = get_db_connection(year)
    try:
        # Check if table/column exists to be safe
        try:
            con.execute(f'SELECT "{column}" FROM main LIMIT 1')
        except:
            return [] # Return empty if column invalid

        # Fetch distinct values for the dropdown
        query = f'SELECT DISTINCT "{column}" FROM main WHERE "{column}" IS NOT NULL ORDER BY "{column}" ASC'
        result = con.execute(query).fetchall()
        return [r[0] for r in result]
    except:
        return []
    finally:
        con.close()

@app.get("/query/{year}")
def query_data(year: str, request: Request, limit: int = 100, filter_col: str = None, filter_val: str = None, translate: bool = Query(False)):
    """
    'last_updated' is automatically the first column (Left Most).
    Retrieves the latest data snapshot from the 'main' table.
    Includes basic string filtering and JSON NaN sanitization.
    """
    con, _ = get_db_connection(year)
    try:
        # Ensure database is initialized before querying
        tables = con.execute("SHOW TABLES").fetchall()
        if not tables or ('main',) not in tables:
            return JSONResponse(
             status_code=404, 
             content={"error": "Table 'main' not found. Please upload data first."}
            )

        # Build Query
        base_query = "SELECT * FROM main"
        # Convert query_params to dict
        params_dict = dict(request.query_params)
        
        final_query, values = build_dynamic_query(con, base_query, params_dict)
        # Add Sort and Limit
        final_query += f" ORDER BY last_updated DESC LIMIT {limit}"

        
        # Execute and return Polars DataFrame
        result = con.execute(final_query, values).pl()
        
        # Formatting:
        # 1. Cast Timestamp to String (JSON doesn't support native datetime objects)
        result = result.with_columns(pl.col("last_updated").cast(pl.String))
        
        # 2. Convert to Dictionary with OPTIONAL Middleware (Slower, only if requested)
        if translate:
            result = apply_recommendations(result)
        # if not middleware, skip directly to dict conversion
        data_dict = result.to_dict(as_series=False)
        
        # 3. Sanitize NaNs:
        # JSON standard forbids NaN. Python's `json` module allows it but frontend JS will crash.
        # We manually iterate to replace float('nan') with None (which becomes JSON null).
        data_dict = result.to_dict(as_series=False)
        clean_data = {}
        for k, v_list in data_dict.items():
            clean_list = []
            for val in v_list:
                # Check for float NaN
                if isinstance(val, float) and math.isnan(val):
                    clean_list.append(None)
                else:
                    clean_list.append(val)
            clean_data[k] = clean_list

        return JSONResponse(content=clean_data)

    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        con.close()

@app.get("/download/{year}")
def download_data(year: str, background_tasks: BackgroundTasks, request: Request, translate: bool = False):
    """
    Export Endpoint:
    1. Reads DuckDB.
    2. Writes to temporary Excel.
    3. Returns file to user.
    4. Deletes temporary file after response is sent.
    """
    con, db_path = get_db_connection(year)
    temp_filename = f"export_{year}.xlsx"
    
    try:
        tables = con.execute("SHOW TABLES").fetchall()
        if not tables or ('main',) not in tables:
             return JSONResponse(status_code=404, content={"error": "No data found for this year."})

        # Build Query with SAME filters as View
        base_query = "SELECT * FROM main"
        params_dict = dict(request.query_params)
        
        final_query, values = build_dynamic_query(con, base_query, params_dict)
        
        # Add Sort
        final_query += " ORDER BY last_updated DESC"

        # Execute
        df = con.execute(final_query, values).pl()
        
        if "last_updated" in df.columns:
            df = df.drop(["last_updated", "source_file"])

        # OPTIONAL Middleware
        if translate:
            df = apply_recommendations(df)

        # Write Excel
        df.write_excel(temp_filename)

        # Schedule deletion
        background_tasks.add_task(os.remove, temp_filename)

        return FileResponse(
            path=temp_filename,
            filename=f"Data_Wilayah_{year}.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        traceback.print_exc()
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        con.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
