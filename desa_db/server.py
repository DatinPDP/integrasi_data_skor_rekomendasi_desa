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
import hashlib
from pydantic import BaseModel
from datetime import datetime, timedelta
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
 
import duckdb
import polars as pl
from fastapi import FastAPI, UploadFile, File, Form, Query, Request, Depends, BackgroundTasks, HTTPException, status
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException # For 404 handler

# IMPORTS FOR AUTH
from auth import auth_verify_password, auth_create_access_token, auth_get_current_user, auth_get_users_db, ACCESS_TOKEN_EXPIRE_MINUTES
 
# /root
#   /root
#   /.config/rekomendasi.json
#   /.config/headers.txt
#   /.config/intervensi_kegiatan.json
#   /.config/table_structure.csv
#   /desa_db/server.py
#   /desa_db/middleware.py
#   /front_end/router.py
#   /front_end/templates/admin.html
#   /front_end/templates/login.html
 
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
    # MUST list specific ports. Wildcard "*" will BLOCK cookies.
    allow_origins=[
        "http://localhost:8001",
        "http://127.0.0.1:8001",
        "http://localhost:8000",
        "http://127.0.0.1:8000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Allow JS to read this specific header
    expose_headers=["X-Total-Count"]
)


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
        helpers_internal_process_staging_file,
        helpers_build_dynamic_query,
        helpers_get_cache_path,
        helpers_get_or_create_intervensi_kegiatan,
        helpers_calculate_dashboard_stats,
        ID_COL,
        BASE_DIR as MW_BASE_DIR,
        CONFIG_DIR,
        STAGING_FOLDER as MW_STAGING_FOLDER
    )
except ImportError:
    # Fallback for different context import
    from desa_db.middleware import apply_rekomendasis, make_json_response, helpers_get_db_connection
    from desa_db.middleware import helpers_init_db, helpers_internal_process_staging_file
    from desa_db.middleware import helpers_build_dynamic_query, helpers_get_cache_path
    from desa_db.middleware import ID_COL, BASE_DIR as MW_BASE_DIR, CONFIG_DIR
 
# ==========================================
# PATH CONFIGURATION (ABSOLUTE PATHS)
# ==========================================
 
# Get the directory where server.py is located (e.g., C:/.../desa_db)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Temp folder for uploads
STAGING_FOLDER = os.path.join(BASE_DIR, "staging")

# DEFINE TEMPLATE PATHS
# Resolves to: /.../front_end/templates
ROOT_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))
TEMPLATE_DIR = os.path.join(ROOT_DIR, "front_end", "templates")
 
# Ensure directories exist
os.makedirs(STAGING_FOLDER, exist_ok=True)
os.makedirs(CONFIG_DIR, exist_ok=True)
os.makedirs(TEMPLATE_DIR, exist_ok=True)
os.makedirs(ROOT_DIR, exist_ok=True)
 
# ==========================================
# Login, logout, 404, Endpoints
# ==========================================
class LoginRequest(BaseModel):
    username: str
    password: str

@app.post("/api/login")
async def login(creds: LoginRequest, response: JSONResponse = None):
    users_db = auth_get_users_db()
    user = users_db.get(creds.username)

    if not user or not auth_verify_password(creds.password, user['hash']):
        return JSONResponse(status_code=401, content={"error": "Invalid credentials"})

    # Generate JWT
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth_create_access_token(
        data={"sub": creds.username, "role": user['role']},
        expires_delta=access_token_expires
    )

    # Return success AND Set HttpOnly Cookie
    resp = JSONResponse(content={"message": "Login successful", "role": user['role']})
    resp.set_cookie(
        key="session_token", 
        value=access_token, 
        httponly=True,   # JavaScript cannot read this (Security +)
        max_age=86400,   # 1 day
        # ESSENTIAL FOR CLOUDFLARE TUNNELS (Different Domains):
        samesite="none", 
        secure=True      
    )
    return resp

@app.post("/api/logout")
async def logout():
    resp = JSONResponse(content={"message": "Logged out"})
    resp.delete_cookie(
        key="session_token", 
        httponly=True, 
        samesite="none", 
        secure=True
    )
    return resp

# 404 handler
@app.exception_handler(404)
async def custom_404_handler(request, exc):
    # Returns the HTML page instead of JSON {"detail": "Not Found"}
    return FileResponse(os.path.join(TEMPLATE_DIR, "404.html"), status_code=404)

# LOGIN PAGE (Public)
@app.get("/login", response_class=HTMLResponse)
async def get_login_page():
    return FileResponse(os.path.join(TEMPLATE_DIR, "login.html"))

# ADMIN PAGE (Protected)
@app.get("/admin", response_class=HTMLResponse)
async def get_admin_page(request: Request):
    """
    Server-Side Protection:
    Checks if the 'session_token' cookie exists. 
    If not, redirects to /login immediately.
    """
    token = request.cookies.get("session_token")
    
    if not token:
        # User is not logged in -> Redirect
        return RedirectResponse(url="/login")
    
    # User has a cookie -> Serve the page
    # (The API endpoints will still verify if the token is valid/expired)
    return FileResponse(os.path.join(TEMPLATE_DIR, "admin.html"))

# ROOT REDIRECT
@app.get("/")
async def root_redirect():
    return RedirectResponse(url="/admin")

# ==========================================
# API Endpoints
# ==========================================
# Table Structure Endpoints
@app.get("/config/table_structure", dependencies=[Depends(auth_get_current_user)])
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
            try: dialect = sniffer.sniff(sample, delimiters=";")
            except: dialect = None
 
            reader = csv.DictReader(f, delimiter=dialect.delimiter if dialect else ";")
            data = list(reader)
 
        return JSONResponse(content=data)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
 
# Resumable Uploads Endpoints
class UploadInit(BaseModel):
    filename: str
    file_uid: str
    total_size: int
    total_hash: str
 
class UploadFinalize(BaseModel):
    upload_id: str
    filename: str
    total_hash: str
 
# Resumable Uploads Endpoints
@app.post("/upload/init/{year}", dependencies=[Depends(auth_get_current_user)])
async def endpoint_upload_init(year: str, payload: UploadInit):
    """
    Checks if an upload was interrupted and returns the offset to resume from.
    """
    # Use file_uid (hash+size) to track partial uploads
    temp_file_path = os.path.join(STAGING_FOLDER, f"partial_{payload.file_uid}.tmp")
 
    received_bytes = 0
    if os.path.exists(temp_file_path):
        received_bytes = os.path.getsize(temp_file_path)
 
        # If file is complete, verify hash immediately
        if received_bytes == payload.total_size:
            with open(temp_file_path, "rb") as f:
                existing_hash = hashlib.md5(f.read()).hexdigest()
            if existing_hash == payload.total_hash:
                return {"status": "exists", "upload_id": payload.file_uid, "received_bytes": received_bytes}
            else:
                # Corrupt/Different file? Restart.
                os.remove(temp_file_path)
                received_bytes = 0
 
    return {"status": "ready", "upload_id": payload.file_uid, "received_bytes": received_bytes}
 
# Resumable Uploads Endpoints
@app.post("/upload/chunk/{year}", dependencies=[Depends(auth_get_current_user)])
async def endpoint_upload_chunk(
    year: str,
    chunk: UploadFile = File(...),
    upload_id: str = Form(...),
    offset: int = Form(...),
    chunk_hash: str = Form(...)
):
    """
    Appends a binary chunk to the temp file.
    Validates the chunk's integrity via MD5 before writing.
    """
    temp_file_path = os.path.join(STAGING_FOLDER, f"partial_{upload_id}.tmp")
 
    # Read chunk content
    content = await chunk.read()
 
    # Integrity Check (Chunk Hash)
    server_chunk_hash = hashlib.md5(content).hexdigest()
    if server_chunk_hash != chunk_hash:
        return JSONResponse(status_code=400, content={"error": "Chunk Corruption detected (Hash Mismatch)"})
 
    # Append to file
    # 'ab' = Append Binary. We trust the 'offset' provided by client matches file size
    # In a stricter system, we'd check os.path.getsize(temp_file_path) == offset
    with open(temp_file_path, "ab") as f:
        # Seek is redundant in 'ab' mode usually, but ensures safety if file implementation varies
        # f.seek(offset) 
        f.write(content)
 
    return {"status": "ok", "received": len(content)}
 
# Resumable Uploads Endpoints
@app.post("/upload/finalize/{year}", dependencies=[Depends(auth_get_current_user)])
async def endpoint_upload_finalize(year: str, payload: UploadFinalize):
    """
    Triggered when all chunks are sent. 
    1. Validates Total File Hash.
    2. Runs the heavy Parser/Diff logic.
    """
    temp_file_path = os.path.join(STAGING_FOLDER, f"partial_{payload.upload_id}.tmp")
 
    if not os.path.exists(temp_file_path):
         return JSONResponse(status_code=404, content={"error": "Upload not found"})
 
    # Validate Total Integrity
    # Note: On very slow CPUs/Large files, this might take a second.
    with open(temp_file_path, "rb") as f:
        final_hash = hashlib.md5(f.read()).hexdigest()
 
    if final_hash != payload.total_hash:
        return JSONResponse(status_code=400, content={"error": "Final File Corruption (MD5 Mismatch)"})
 
    # Process (The Heavy Lifting)
    # Generate a unique staging ID for the DB logic
    staging_id = str(uuid.uuid4())
 
    try:
        # Call the Helper
        result = helpers_internal_process_staging_file(year, temp_file_path, payload.filename, staging_id)
 
        # Cleanup partial file upon success
        os.remove(temp_file_path)
 
        return result
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})
 
# STAGE: Upload -> Analyze Diff -> Return Stats
@app.post("/stage/{year}", dependencies=[Depends(auth_get_current_user)])
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
    Legacy simple upload (kept for compatibility or small files).
    Now just wrappers the internal helper.
    """
 
    # Security: Sanitize filename
    staging_id = str(uuid.uuid4())
    # Preserve extension so Calamine knows if it's xlsx or xlsb
    _, ext = os.path.splitext(file.filename)
    if not ext: ext = ".xlsb"
    temp_path = os.path.join(STAGING_FOLDER, f"temp_legacy_{staging_id}{ext}")
 
    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
 
        return helpers_internal_process_staging_file(year, temp_path, file.filename, staging_id)
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        if os.path.exists(temp_path): os.remove(temp_path)
 
# COMMIT: Apply the Staged Changes
@app.post("/commit/{year}", dependencies=[Depends(auth_get_current_user)])
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
 
        # Close REMOVED rows (Set valid_to = now)
        con.execute(f"""
            UPDATE master_data SET valid_to = '{now}'
            WHERE valid_to IS NULL 
            AND "{ID_COL}" NOT IN (SELECT "{ID_COL}" FROM incoming)
        """)
 
        # Close UPDATED rows (Set valid_to = now)
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
 
        # Insert NEW and UPDATED versions (Set valid_from = now, valid_to = NULL)
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
 
        return {"status": "success", "message": "Database updated successfully."}
 
    except Exception as e:
        con.execute("ROLLBACK")
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        con.close()
        if os.path.exists(temp_path): os.remove(temp_path)
 
# QUERY: Supports Time Travel via 'version' (Timestamp)
@app.get("/query/{year}", dependencies=[Depends(auth_get_current_user)])
def endpoint_get_query_data(
    year: str,
    request: Request,
    limit: int = 10000,
    offset: int = 0,
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
    2. **Dynamic Filtering**: Automatically converts URL parameters into SQL `WHERE` clauses 
        (e.g., `?Provinsi=X` becomes `WHERE "Provinsi" ILIKE '%X%'`).
    3. **Data Translation**: Optionally converts numeric scores (e.g., 1-5) into human-readable
        text recommendations if `translate=True`.
    4. **Performance**: Bypasses standard Pydantic serialization by streaming the Polars DataFrame
        directly to JSON (optimized for Gzip compression).
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
 
        # GET TRUE TOTAL COUNT (Before Limit/Offset)
        # wrap the final query to count rows that match filters
        count_sql = f"SELECT COUNT(*) FROM ({final_query})"
        total_rows = con.execute(count_sql, values).fetchone()[0]

        # SORTING LOGIC (AG Grid Support)
        sort_by = params_dict.get("sort_by")
        sort_dir = params_dict.get("sort_dir", "asc")

        # Default stable sort if nothing selected
        order_clause = f'ORDER BY "{ID_COL}" ASC'

        if sort_by:
            # Security: Validate column exists to prevent SQL Injection
            # "DESCRIBE" is fast in DuckDB
            try:
                valid_cols = [r[0] for r in con.execute("DESCRIBE master_data").fetchall()]
                
                if sort_by in valid_cols:
                    safe_dir = "DESC" if sort_dir.lower() == "desc" else "ASC"
                    # sort to ensure pages don't shuffle rows. 
                    # Using ID_COL or rowid if available, but valid_from/Provinsi is a safe fallback.
                    # add ID_COL as a secondary sort key to ensure consistent pagination 
                    # even if values in the primary column are identical.
                    order_clause = f'ORDER BY "{sort_by}" {safe_dir}, "{ID_COL}" ASC'
            except Exception as e:
                print(f"Sorting Error (Ignored): {e}")

        # Append Sort + Pagination
        final_query += f" {order_clause} LIMIT {limit} OFFSET {offset}"
 
        res = con.execute(final_query, values).pl()
        if translate: res = apply_rekomendasis(res)
 
        # Sanitize NaNs
        records = res.to_dicts()
        clean = [{k: (None if isinstance(v, float) and math.isnan(v) else v) for k,v in r.items()} for r in records]
        # Return with header
        # Instead of make_json_response (which returns Response), we use JSONResponse 
        # so we can easily attach headers while keeping the data structure.
        # OR use make_json_response and attach headers.
        
        response = make_json_response(res) 
        response.headers["X-Total-Count"] = str(total_rows)
        return response
 
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        con.close()
 
# VERSIONS LIST
@app.get("/history/versions/{year}", dependencies=[Depends(auth_get_current_user)])
def endpoint_get_history_versions(year: str):
    """
    Returns metadata for initialization:
    1. List of versions (commits)
    2. Hierarchy tree (Prov -> Kab -> Kec) built live from DuckDB
    """
    con, _ = helpers_get_db_connection(year)
    response_data = {
        "versions": [],
        "hierarchy": {}
    }
 
    try:
        # Fetch Versions
        try:
            commits = con.execute("SELECT timestamp, filename FROM commits ORDER BY timestamp DESC").fetchall()
            response_data["versions"] = [{"ts": str(r[0]), "label": f"{r[0]} - {r[1]}"} for r in commits]
        except duckdb.CatalogException:
            # Table might not exist yet if fresh install
            pass
 
        # Fetch Hierarchy (Live Distinct Query)
        try:
            # Check if master_data exists first
            tables = [t[0] for t in con.execute("SHOW TABLES").fetchall()]
            if 'master_data' in tables:
                query = """
                    SELECT DISTINCT "Provinsi", "Kabupaten/ Kota", "Kecamatan" 
                    FROM master_data
                    WHERE valid_to IS NULL AND "Provinsi" IS NOT NULL
                    ORDER BY "Provinsi", "Kabupaten/ Kota", "Kecamatan"
                """
                rows = con.execute(query).fetchall()
 
                # Build Tree
                tree = {}
                for prov, kab, kec in rows:
                    if prov not in tree: tree[prov] = {}
                    if kab not in tree[prov]: tree[prov][kab] = []
                    if kec not in tree[prov][kab]: tree[prov][kab].append(kec)
 
                response_data["hierarchy"] = tree
        except Exception as e:
            print(f"Hierarchy Error: {e}")
 
        return response_data
 
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        con.close()

# Download server-side endpoints
@app.get("/download/excel/{year}", dependencies=[Depends(auth_get_current_user)])
def endpoint_download_server_excel(year: str, request: Request):
    """
    Generates a 2-Sheet Excel file (Grid Data + Dashboard Stats)
    Generates Excel Export matching Frontend styles.
    applying ALL current filters and sorting from the frontend.
    """
    con, _ = helpers_get_db_connection(year)
    
    try:
        # ==========================================
        # PREPARE QUERY (Filters + Sort)
        # ==========================================
        params_dict = dict(request.query_params)
        
        # Check Translate Flag (String "true"/"false" from URL)
        do_translate = params_dict.get("translate", "false").lower() == "true"

        # Time Travel Filter
        version = params_dict.get("version")
        time_filter = f"valid_from <= '{version}' AND (valid_to > '{version}' OR valid_to IS NULL)" if version else "valid_to IS NULL"
        
        base_query = f"SELECT * EXCLUDE (valid_from, valid_to, commit_id, source_file) FROM master_data WHERE {time_filter}"
        
        # Apply Filters (Provinsi, Kab, Kec, etc.)
        final_query, values = helpers_build_dynamic_query(con, base_query, params_dict)

        # Apply Sort (AG Grid State)
        sort_by = params_dict.get("sort_by")
        sort_dir = params_dict.get("sort_dir", "asc")
        
        if sort_by:
            try:
                # Basic injection check
                valid_cols = [r[0] for r in con.execute("DESCRIBE master_data").fetchall()]
                if sort_by in valid_cols:
                    safe_dir = "DESC" if sort_dir.lower() == "desc" else "ASC"
                    final_query += f' ORDER BY "{sort_by}" {safe_dir}, "{ID_COL}" ASC'
            except: pass
        else:
            final_query += f' ORDER BY "{ID_COL}" ASC'

        # Fetch Data (No Limit)
        df_grid = con.execute(final_query, values).pl()

        # APPLY TRANSLATION IF REQUESTED (Sheet 1 Fix)
        if do_translate:
            df_grid = apply_rekomendasis(df_grid)

        # ==========================================
        # BUILD EXCEL (OpenPyXL)
        # ==========================================
        wb = Workbook()
        
        # Define Common Styles
        thin_border = Border(left=Side(style='thin'), right=Side(style='thin'), top=Side(style='thin'), bottom=Side(style='thin'))
        align_top = Alignment(vertical='top', wrap_text=True)
        align_center = Alignment(horizontal='center', vertical='center', wrap_text=True)
        header_fill = PatternFill(start_color="F2F2F2", end_color="F2F2F2", fill_type="solid")
        header_font = Font(bold=True)

        # --- SHEET 1: GRID DATA ---
        ws1 = wb.active
        ws1.title = "Grid Data"
        df_sheet1 = apply_rekomendasis(df_grid) if do_translate else df_grid
        grid_dicts = df_sheet1.to_dicts()
        
        # Write Headers
        grid_dicts = df_grid.to_dicts()
        if grid_dicts:
            headers = list(grid_dicts[0].keys())
            ws1.append(headers)
            for row in grid_dicts:
                # Handle None/NaN for Excel
                clean_row = [(v if v is not None else "") for v in row.values()]
                ws1.append(clean_row)
            
            # Basic Formatting for Sheet 1
            for cell in ws1[1]:
                cell.font = header_font
                cell.fill = header_fill
        else:
            ws1.append(["No Data Found for filters"])

        # --- SHEET 2: DASHBOARD STATS ---
        ws2 = wb.create_sheet("Dashboard Calc")

        # A. LOAD CONFIG & TEMPLATES
        csv_path = os.path.join(CONFIG_DIR, "table_structure.csv")
        structure = []
        if os.path.exists(csv_path):
            with open(csv_path, "r", encoding="utf-8-sig", errors="replace") as f:
                # Auto-detect delimiter
                sample = f.read(1024)
                f.seek(0)
                sniffer = csv.Sniffer()
                try: dialect = sniffer.sniff(sample, delimiters=";")
                except: dialect = None
                reader = csv.DictReader(f, delimiter=dialect.delimiter if dialect else ";")
                structure = list(reader)

        # Get Metrics Columns (Same logic as dashboard endpoint)
        db_cols_info = con.execute("DESCRIBE master_data").fetchall()
        metadata_cols = {
            "valid_from", "valid_to", "commit_id", "source_file",
            "Provinsi", "Kabupaten/ Kota", "Kecamatan", 
            "Kode Wilayah Administrasi Desa", "Desa", "TAHUN DATA"
        }
        ordered_db_cols = [r[0] for r in db_cols_info if r[0] not in metadata_cols]

        # Load Narrative Templates
        item_names = [row.get("ITEM", "") for row in structure if row.get("ITEM")]
        templates = helpers_get_or_create_intervensi_kegiatan(item_names)

        # *** CALL HELPER ***
        calculated_rows = helpers_calculate_dashboard_stats(df_grid, structure, ordered_db_cols, templates)

        # B. SETUP COLUMNS & HEADERS
        # Set Widths (Approximating CSS pixels to Excel chars)
        # 40px ~= 5 chars, 300px ~= 40 chars, 1100px ~= 100 chars
        ws2.column_dimensions['A'].width = 5   # NO
        ws2.column_dimensions['B'].width = 15  # DIMENSI
        ws2.column_dimensions['C'].width = 15  # SUB
        ws2.column_dimensions['D'].width = 15  # INDIKATOR
        ws2.column_dimensions['E'].width = 45  # ITEM (Wide)
        for c in ['F','G','H','I','J','K']:
            ws2.column_dimensions[c].width = 8 # Scores
        ws2.column_dimensions['L'].width = 100 # INTERVENSI (Very Wide)

        # Pelaksana Columns
        for c in ['M','N','O','P','Q']:
            ws2.column_dimensions[c].width = 25

        # Write Headers (Rows 1 & 2)
        # Row 1: Merged Headers
        ws2.append(["NO", "DIMENSI", "SUB DIMENSI", "INDIKATOR", "ITEM", 
                    "SKOR", "", "", "", "", "",         # Colspan 6
                    "INTERVENSI",                       # Rowspan 2
                    "PELAKSANA", "", "", "", ""])       # Colspan 5
        
        # Row 2: Sub Headers
        ws2.append(["", "", "", "", "", 
                    "Rata-Rata", "1", "2", "3", "4", "5", 
                    "", 
                    "PUSAT", "PROVINSI", "KABUPATEN", "DESA", "LAINNYA"])

        # Merge Logic for Header
        ws2.merge_cells("A1:A2") # NO
        ws2.merge_cells("B1:B2") # DIM
        ws2.merge_cells("C1:C2") # SUB
        ws2.merge_cells("D1:D2") # IND
        ws2.merge_cells("E1:E2") # ITEM
        ws2.merge_cells("F1:K1") # SKOR Group
        ws2.merge_cells("L1:L2") # INTERVENSI
        ws2.merge_cells("M1:Q1") # PELAKSANA Group

        # Style Headers
        for r in [1, 2]:
            for cell in ws2[r]:
                cell.font = header_font
                cell.fill = header_fill
                cell.border = thin_border
                cell.alignment = align_center

        # Write Data
        merge_tracker = {0: {"val": None, "start": 3}, 1: {"val": None, "start": 3}, 2: {"val": None, "start": 3}, 3: {"val": None, "start": 3}}
        start_row_idx = 3 # Excel starts at row 2 (row 1 is header)

        for i, row in enumerate(calculated_rows):
            current_excel_row = start_row_idx + i
            
            # Extract values from the dictionary returned by the helper
            row_values = [
                row.get("NO"), row.get("DIMENSI"), row.get("SUB DIMENSI"), row.get("INDIKATOR"), row.get("ITEM"),
                row.get("SKOR Rata-Rata"), row.get("SKOR 1"), row.get("SKOR 2"), row.get("SKOR 3"), row.get("SKOR 4"), row.get("SKOR 5"),
                row.get("INTERVENSI KEGIATAN"),
                row.get("PELAKSANA KEGIATAN PUSAT"), row.get("PELAKSANA KEGIATAN PROVINSI"), 
                row.get("PELAKSANA KEGIATAN KABUPATEN"), row.get("PELAKSANA KEGIATAN DESA"), 
                row.get("PELAKSANA KEGIATAN Lainnya")
            ]

            ws2.append(row_values)

            # Styling (Borders & Alignment)
            for col_idx, cell in enumerate(ws2[current_excel_row], 1):
                cell.border = thin_border
                cell.alignment = align_top # Top align is crucial for merged cells
                
                # Center align the Score columns (F to K -> 6 to 11)
                if 6 <= col_idx <= 11:
                    cell.alignment = Alignment(horizontal='center', vertical='top')

            # Merging Logic
            # Iterate through mergeable columns (NO, DIMENSI, SUB, INDIKATOR)
            # Logic: If value changes OR parent value changed, trigger merge of previous block and start new.
            meta_vals = [row.get("NO"), row.get("DIMENSI"), row.get("SUB DIMENSI"), row.get("INDIKATOR")]
            for col_idx in [0, 1, 2, 3]: 
                val = meta_vals[col_idx]
                
                # Check if parent changed (e.g., Cant merge SUB DIMENSI if DIMENSI changed)
                parent_changed = any(meta_vals[p] != merge_tracker[p]["val"] for p in range(col_idx))
                
                if val != merge_tracker[col_idx]["val"] or parent_changed or (i == len(calculated_rows) - 1):
                    # Merge the PREVIOUS block if it spanned more than 1 row
                    prev_end = current_excel_row - 1 if not (i == len(calculated_rows) - 1) else current_excel_row
                    prev_start = merge_tracker[col_idx]["start"]
                    
                    if prev_end > prev_start:
                        col_letter = get_column_letter(col_idx + 1)
                        ws2.merge_cells(f"{col_letter}{prev_start}:{col_letter}{prev_end}")
                    
                    # Reset tracker
                    merge_tracker[col_idx]["val"] = val
                    merge_tracker[col_idx]["start"] = current_excel_row

        # ==========================================
        # 3. RETURN FILE
        # ==========================================
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        filename = f"Export_{params_dict.get('Provinsi', 'All')}_{year}.xlsx"
        
        # Return as downloadable file
        return StreamingResponse(
            output, 
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        con.close()
 
# ==========================================
# CALCULATION & DASHBOARD LOGIC
# ==========================================
 
# CALCULATION
@app.post("/dashboard/calculate/{year}", dependencies=[Depends(auth_get_current_user)])
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
 
        # Load CSV Structure
        csv_path = os.path.join(CONFIG_DIR, "table_structure.csv")
        if not os.path.exists(csv_path):
            return JSONResponse(status_code=404, content={"error": "table_structure.csv missing"})
 
        with open(csv_path, "r", encoding="utf-8-sig", errors="replace") as f:
            sniffer = csv.Sniffer()
            sample = f.read(1024)
            f.seek(0)
            try: dialect = sniffer.sniff(sample, delimiters=";")
            except: dialect = None
            reader = csv.DictReader(f, delimiter=dialect.delimiter if dialect else ";")
            structure = list(reader)
 
        # Get Ordered Metric Columns from DB
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
 
        # Load/Init Templates
        item_names = [row.get("ITEM", "") for row in structure if row.get("ITEM")]
        templates = helpers_get_or_create_intervensi_kegiatan(item_names)
 
        # Calculate Per Row (Using helpers)
        calculated_rows = helpers_calculate_dashboard_stats(df_filtered, structure, ordered_db_cols, templates)
 
        # Format for Frontend (Ensure numbers are strings with commas if needed, or send raw)
        # The helper sends raw numbers (Int/Float). 
        # If your frontend expects formatted strings (e.g. "1,024"), convert here or handle in JS.
        # Current frontend code handles raw numbers fine.
        return JSONResponse(content=calculated_rows)
 
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        con.close()
 
# DELETE: Soft Delete (Expire) specific IDs
@app.post("/delete/{year}", dependencies=[Depends(auth_get_current_user)])
async def endpoint_post_delete_ids(
    year: str,
    ids: str = Query(..., description="Semicolon or newline separated list of IDs"),
    summary: str = Query("Manual Delete", description="Reason for deletion"),
    # We can inject the user info if we want to log WHO deleted it
    current_user: str = Depends(auth_get_current_user)
    ):
    """
    Soft-deletes records by setting valid_to = NOW().
    They will no longer appear in 'Live' views but remain in history.
    Includes whitespace cleaning to ensure IDs match.
    """
    con, _ = helpers_get_db_connection(year)
    try:
        # STRICT RULE: Split by SEMICOLON (;) or Newline. NO COMMAS.
        raw_ids = re.split(r'[;\n\r]+', ids)
        # Ensure we are searching for clean, stripped strings
        id_list = [x.strip() for x in raw_ids if x.strip()]
 
        if not id_list:
            return JSONResponse(status_code=400, content={"error": "No valid IDs provided"})
 
        # Execute Soft Delete
        con.execute("BEGIN TRANSACTION")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
 
        # Create SQL list: 'ID1', 'ID2', ...
        id_sql_list = ", ".join([f"'{x}'" for x in id_list])
 
        # ROBUST QUERY:
        # 1. TRIM(CAST(...)): Handles whitespace and ensures we compare strings
        # 2. RETURNING: Captures the IDs that were actually touched
        query = f"""
            UPDATE master_data 
            SET valid_to = '{now}'
            WHERE valid_to IS NULL 
            AND TRIM(CAST("{ID_COL}" AS VARCHAR)) IN ({id_sql_list})
            RETURNING "{ID_COL}"
        """
 
        # Debugging: 
        # print(f"Executing Delete: {query}")
 
        # Execute and fetch the IDs that were actually updated
        deleted_rows = con.execute(query).fetchall()
        changes = len(deleted_rows)
 
        if changes > 0:
            # Log the Commit (using uuid for consistency)
            commit_id = str(uuid.uuid4())
            con.execute(f"INSERT INTO commits VALUES ('{commit_id}', '{now}', 'Manual Delete', '{summary} ({changes} rows)')")
            con.execute("COMMIT")
 
            print(current_user," changes ", commit_id)
            return {
                "status": "success", 
                "deleted_count": changes, 
                "deleted_ids": [r[0] for r in deleted_rows]
            }
        else:
            con.execute("ROLLBACK")
            # IMPORTANT: This returns 200 OK, but with a warning status.
            # The frontend must read this 'status' field.
            return {
                "status": "warning", 
                "message": "No active records found. Check if ID has hidden spaces or is already deleted."
            }
 
    except Exception as e:
        con.execute("ROLLBACK")
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        con.close()
 
# Check diff version sidebar
@app.get("/history/details/{year}", dependencies=[Depends(auth_get_current_user)])
def endpoint_get_history_details(year: str, version: str = Query(...)):
    """
    Calculates the 'Git Diff' for a specific commit version.
    1. Finds rows that EXPIRED at this timestamp (Old State).
    2. Finds rows that STARTED at this timestamp (New State).
    3. Compares them to determine: ADDED, DELETED, or MODIFIED.
    """
    con, _ = helpers_get_db_connection(year)
    try:
        # Fetch Old State (Rows valid_to = version)
        old_rows_df = con.execute(f"SELECT * FROM master_data WHERE valid_to = ?", [version]).pl()
 
        # Fetch New State (Rows valid_from = version)
        new_rows_df = con.execute(f"SELECT * FROM master_data WHERE valid_from = ?", [version]).pl()
 
        # Convert to Dictionary { ID: {row_data} }
        # Uses ID_COL from middleware (Kode Wilayah Administrasi Desa)
        old_map = {str(row[ID_COL]): row for row in old_rows_df.to_dicts()}
        new_map = {str(row[ID_COL]): row for row in new_rows_df.to_dicts()}
 
        changes = []
        ignored_cols = ["valid_from", "valid_to", "commit_id", "source_file"]
 
        # A. Detect MODIFIED and ADDED
        for uid, new_row in new_map.items():
            if uid in old_map:
                # It existed before -> Check for MODIFICATIONS
                old_row = old_map[uid]
                diffs = []
                for k, v in new_row.items():
                    if k not in ignored_cols and old_row.get(k) != v:
                        diffs.append(k)
 
                if diffs:
                    changes.append({
                        "type": "MOD", 
                        "id": uid, 
                        "desc": f"Updated headers:\n- " + "\n- ".join(diffs)
                    })
            else:
                # It did not exist before -> ADDED
                changes.append({
                    "type": "ADD", 
                    "id": uid, 
                    "desc": "New Record Added"
                })
 
        # B. Detect DELETED (In Old but NOT in New)
        for uid in old_map:
            if uid not in new_map:
                changes.append({
                    "type": "DEL", 
                    "id": uid, 
                    "desc": f"Dropped (Valid To: {version})"
                })
 
        # Safety: Limit to first 9999 changes to prevent UI crash on massive uploads
        if len(changes) > 9999:
            remaining = len(changes) - 9999
            changes = changes[:9999]
            changes.append({"type": "INFO", "id": "...", "desc": f"...and {remaining} more changes"})
 
        return JSONResponse(content={"changes": changes})
 
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        con.close()
 
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
