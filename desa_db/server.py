import os
import shutil
import math
import traceback
import json
import re
import uuid
import glob
import csv
import numpy as np
import io
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

import duckdb
import polars as pl
from fastapi import FastAPI, UploadFile, File, Query, Request, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

# /root
#   /.config/rekomendasi.json
#   /root
#   /.config/headers.txt
#   /.config/intervensi_kegiatan.json
#   /.config/recommendation.json
#   /.config/table_structure.csv
#   /desa_db/server.py
#   /desa_db/middleware.py
#   /front_end/web.py
#   /front_end/templates/admin.html
#   /front_end/templates/login.html

# ==========================================
# Configuration & Constants
# ==========================================
# Import helpers and logic from middleware
try:
    from middleware import (
        apply_rekomendasis, 
        make_json_response,
        helpers_get_db_connection,
        helpers_init_db,
        helpers_refresh_filter_cache,
        helpers_build_dynamic_query,
        helpers_get_cache_path,
        ID_COL,
        BASE_DIR as MW_BASE_DIR, # Import BASE_DIR to ensure alignment
        CONFIG_DIR,
        STAGING_FOLDER as MW_STAGING_FOLDER # You might need to add STAGING_FOLDER to middleware or keep it here
    )
except ImportError:
    # Fallback for different context import
    from desa_db.middleware import apply_rekomendasis, make_json_response, helpers_get_db_connection, helpers_init_db, helpers_refresh_filter_cache, helpers_build_dynamic_query, helpers_get_cache_path, ID_COL, BASE_DIR as MW_BASE_DIR, CONFIG_DIR

app = FastAPI()

# ==========================================
# MIDDLEWARE SETUP
# ==========================================

# GZIP COMPRESSION (Solves the 100MB issue)
# minimum_size=1000 means responses smaller than 1kb won't be compressed.
app.add_middleware(GZipMiddleware, minimum_size=1000)

# CORS
# CHECK: REMOVE ON PROD;Allow Frontend (8001) to talk to Backend (8000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify ["http://localhost:8001"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ==========================================
# PATH CONFIGURATION (ABSOLUTE PATHS)
# ==========================================

# Get the directory where server.py is located (e.g., C:/.../desa_db)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Temp folder for uploads
STAGING_FOLDER = os.path.join(BASE_DIR, "staging")

# Header File: inside .config/headers.txt (sibling of desa_db)
HEADER_FILE = os.path.join(CONFIG_DIR, "headers.txt")

# Ensure directories exist
os.makedirs(STAGING_FOLDER, exist_ok=True)
os.makedirs(CONFIG_DIR, exist_ok=True)

# ==========================================
# API Endpoints
# ==========================================
# Table Structure Endpoints
@app.get("/config/table_structure")
def endpoint_get_table_structure():
    """
    Returns the table_structure.csv as JSON for the frontend dashboard.
    """
    csv_path = os.path.join(CONFIG_DIR, "table_structure.csv")
    
    if not os.path.exists(csv_path):
        return JSONResponse(status_code=404, content={"error": "Config file not found"})
        
    try:
        # Use standard csv library for safety, handle encoding errors
        with open(csv_path, "r", encoding="utf-8-sig", errors="replace") as f:
            # Check delimiter from the first line
            sample = f.read(1024)
            f.seek(0)
            sniffer = csv.Sniffer()
            # Default to semicolon if sniffer fails
            try: dialect = sniffer.sniff(sample, delimiters=";,")
            except: dialect = None
            
            reader = csv.DictReader(f, delimiter=dialect.delimiter if dialect else ";")
            data = list(reader)
            
        return JSONResponse(content=data)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

# STAGE: Upload -> Analyze Diff -> Return Stats
@app.post("/stage/{year}")
async def endpoint_post_stage_upload(
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
        con, db_path = helpers_get_db_connection(year)
        helpers_init_db(con, df.columns)
        
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
async def endpoint_post_commit_stage(
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
        
    con, _ = helpers_get_db_connection(year)
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
        helpers_refresh_filter_cache(year)
        
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
def endpoint_get_query_data(
    year: str,
    request: Request,
    limit: int = 500,
    filter_col: str = None,
    filter_val: str = None,
    translate: bool = False,
    version: str = None
    ):
    """
    OPTIMIZED QUERY ENDPOINT:
    Retrieves a subset of the master data for a specific year with support for historical versioning.

    Key Features:
    1. **Time Travel (SCD Type 2)**: 
       - If `version` is provided, fetches the state of the data exactly as it was at that timestamp.
       - If `version` is NULL, fetches the current active data (`valid_to IS NULL`).
    2. **Dynamic Filtering**: Automatically converts URL parameters into SQL `WHERE` clauses (e.g., `?Provinsi=X` becomes `WHERE "Provinsi" ILIKE '%X%'`).
    3. **Data Translation**: Optionally converts numeric scores (e.g., 1-5) into human-readable text recommendations if `translate=True`.
    4. **Performance**: Bypasses standard Pydantic serialization by streaming the Polars DataFrame directly to JSON (optimized for Gzip compression).
    """
    con, _ = helpers_get_db_connection(year)
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
        final_query, values = helpers_build_dynamic_query(con, base_query, params_dict)
        
        final_query += f" LIMIT {limit}"
        
        res = con.execute(final_query, values).pl()
        if translate: res = apply_rekomendasis(res)
        
        # Sanitize NaNs
        records = res.to_dicts()
        clean = [{k: (None if isinstance(v, float) and math.isnan(v) else v) for k,v in r.items()} for r in records]
        
        return make_json_response(res)

    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        con.close()

# VERSIONS LIST
@app.get("/history/versions/{year}")
def endpoint_get_history_versions(year: str):
    """
    Returns list of source files (versions) uploaded
    """
    con, _ = helpers_get_db_connection(year)
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
def endpoint_get_filter_hierarchy(year: str):
    """
    Returns the full location tree (Prov -> Kab -> Kec)
    """
    cache_path = helpers_get_cache_path(year)
    if os.path.exists(cache_path):
        return FileResponse(cache_path, media_type="application/json")
    return {}

# ==========================================
# CALCULATION & DASHBOARD LOGIC
# ==========================================
INTERVENTION_FILE = os.path.join(CONFIG_DIR, "intervensi_kegiatan.json")

def helpers_get_or_create_intervensi_kegiatan(items: list[str]):
    """
    Loads intervensi_kegiatan. If missing, creates a default file 
    using the ITEM names as keys.
    """
    # 1. Try Load
    if os.path.exists(INTERVENTION_FILE):
        try:
            with open(INTERVENTION_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass # Fallback if corrupt

    # 2. Create Defaults (using rekomendasi.json logic if available, else generic)
    defaults = {}
    
    # Try to load existing rekomendasis to pre-seed
    recs = {}
    rec_path = os.path.join(CONFIG_DIR, "rekomendasi.json")
    if os.path.exists(rec_path):
        try:
            with open(rec_path, "r", encoding="utf-8") as f: recs = json.load(f)
        except: pass

    for item in items:
        # If we have specific logic in rekomendasi.json, map it. 
        # Otherwise create a generic placeholder.
        if item in recs:
            defaults[item] = recs[item]
        else:
            # Generic Fallback Template that is WRONG. 
            # YOU NEED TO EDIT THE TEMPLATE
            defaults[item] = {
                "1": f"Perlu peningkatan {item} (Sangat Kurang)",
                "2": f"Perlu peningkatan {item} (Kurang)",
                "3": f"Perlu peningkatan {item} (Cukup)",
                "4": f"Perlu peningkatan {item} (Baik)",
                "5": None
            }
            
    # 3. Save to Disk
    try:
        with open(INTERVENTION_FILE, "w", encoding="utf-8") as f:
            json.dump(defaults, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ Could not save intervensi_kegiatan: {e}")
        
    return defaults

# CALCULATION
@app.post("/dashboard/calculate/{year}")
async def endpoint_post_calculate_dashboard(year: str, request: Request):
    """
    1. Applies SAME filters as /query endpoint to get filtered DB subset
    2. Loads table_structure.csv
    3. Calculates stats on filtered data
    4. Returns dashboard rows with calculations
    """
    con, _ = helpers_get_db_connection(year)
    
    try:
        # === Filter DB first (same as /query endpoint) ===
        params_dict = dict(request.query_params)
        
        # Build base query with time filter
        version = params_dict.get("version")
        if version:
            time_filter = f"valid_from <= '{version}' AND (valid_to > '{version}' OR valid_to IS NULL)"
        else:
            time_filter = "valid_to IS NULL"
        
        base_query = f"SELECT * FROM master_data WHERE {time_filter}"
        
        # Apply location/id filters (reuse existing helper)
        filtered_query, values = helpers_build_dynamic_query(con, base_query, params_dict)
        
        # Execute query to get filtered dataset
        df_filtered = con.execute(filtered_query, values).pl()
        # === End of filtering ===
        
        # 1. Load CSV Structure
        csv_path = os.path.join(CONFIG_DIR, "table_structure.csv")
        if not os.path.exists(csv_path):
            return JSONResponse(status_code=404, content={"error": "table_structure.csv missing"})
            
        with open(csv_path, "r", encoding="utf-8-sig", errors="replace") as f:
            sniffer = csv.Sniffer()
            sample = f.read(1024)
            f.seek(0)
            try: dialect = sniffer.sniff(sample, delimiters=";,")
            except: dialect = None
            reader = csv.DictReader(f, delimiter=dialect.delimiter if dialect else ";")
            structure = list(reader)

        # 2. Get Ordered Metric Columns from DB
        try:
            # DESCRIBE returns columns in creation order
            db_cols_info = con.execute("DESCRIBE master_data").fetchall()
            # Filter out metadata columns
            metadata_cols = {"valid_from", "valid_to", "commit_id", "source_file"}
            # Exclude Location/Identity columns so Index 0 is the first Score
            metadata_cols = {
                "valid_from", "valid_to", "commit_id", "source_file",
                "Provinsi", "Kabupaten/ Kota", "Kecamatan", 
                "Kode Wilayah Administrasi Desa", "Desa", "TAHUN DATA"
            }
            
            # This list preserves the order of metric columns in the DB
            ordered_db_cols = [r[0] for r in db_cols_info if r[0] not in metadata_cols]
        except:
            return JSONResponse(status_code=500, content={"error": "Database not initialized"})

        # 3. Load/Init Templates
        item_names = [row.get("ITEM", "") for row in structure if row.get("ITEM")]
        templates = helpers_get_or_create_intervensi_kegiatan(item_names)

        # 4. Calculate Per Row (Using INDEX Matching)
        calculated_rows = []
        

        for idx, row in enumerate(structure):
            csv_item = row.get("ITEM", "Unknown Item")

            # Default Empty Stats
            stats = {
                "SKOR Rata-Rata": "",
                "SKOR 1": "", "SKOR 2": "", "SKOR 3": "", "SKOR 4": "", "SKOR 5": "",
                "INTERVENSI KEGIATAN": ""
            }

            # MATCHING LOGIC: Use DB Column at index 'idx'
            if idx < len(ordered_db_cols):
                target_col = ordered_db_cols[idx]
                
                # Use filtered data if provided, otherwise query DB
                try:
                    # Calculate from filtered data
                    if target_col in df_filtered.columns:
                        col_data = df_filtered.select(
                            pl.col(target_col).cast(pl.Int64, strict=False)
                        ).to_series()
                        
                        
                        avg = col_data.mean()
                        c1 = (col_data == 1).sum()
                        c2 = (col_data == 2).sum()
                        c3 = (col_data == 3).sum()
                        c4 = (col_data == 4).sum()
                        c5 = (col_data == 5).sum()
                        
                        if avg is not None: stats["SKOR Rata-Rata"] = round(avg, 2)
                        if c1: stats["SKOR 1"] = f"{c1:,}"
                        if c2: stats["SKOR 2"] = f"{c2:,}"
                        if c3: stats["SKOR 3"] = f"{c3:,}"
                        if c4: stats["SKOR 4"] = f"{c4:,}"
                        if c5: stats["SKOR 5"] = f"{c5:,}"

                        # Narrative Generation
                        narrative_parts = []
                        csv_item_name = row.get("ITEM", "")
                        t_map = templates.get(csv_item_name, {})
                        
                        counts = {1: c1, 2: c2, 3: c3, 4: c4, 5: c5}
                        for score in [1, 2, 3, 4, 5]:
                            cnt = counts[score]
                            txt = t_map.get(str(score))
                            if cnt and cnt > 0 and txt:
                                narrative_parts.append(f"{cnt:,} {txt}")
                        
                        if narrative_parts:
                            stats["INTERVENSI KEGIATAN"] = "\n".join(narrative_parts)
                            
                except Exception as e:
                    print(f"Calc Error on index {idx} ({target_col}): {e}")
            else:
                print(f"⚠️ [WARNING] Index Mismatch: CSV Row {idx} has no corresponding DB column (Out of Bounds).")

            row.update(stats)
            calculated_rows.append(row)

        return JSONResponse(content=calculated_rows)

    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        con.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
