import os
import shutil
import math
import traceback
import json
import re
import uuid
import csv
import io
import hashlib
import time
import threading
import multiprocessing
from pydantic import BaseModel
from datetime import datetime, timedelta
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

import duckdb
import polars as pl
from fastapi import FastAPI, UploadFile, File, Form, Query, Request, Depends, BackgroundTasks, HTTPException, status
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException # For 404 handler
from contextlib import asynccontextmanager

# IMPORTS FOR AUTH
from auth import (
    auth_verify_password,
    auth_create_access_token,
    auth_get_current_user,
    auth_require_admin,
    auth_get_users_db,
    ACCESS_TOKEN_EXPIRE_MINUTES
)

# /root
#   /root
#   /.config/rekomendasi.json
#   /.config/headers.json
#   /.config/intervensi_kegiatan_mapping.json
#   /.config/table_structure.csv
#   /desa_db/server.py
#   /desa_db/middleware.py
#   /front_end/router.py
#   /front_end/templates/admin.html
#   /front_end/templates/user.html
#   /front_end/templates/login.html

def _excel_worker(year):
    """
    Runs in a separate process - all memory freed on exit
    """
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    EXPORT_FOLDER = os.path.abspath(os.path.join(BASE_DIR, "../exports"))
    
    target_file = os.path.join(EXPORT_FOLDER, f"Export_Nasional_{year}_skor.xlsx")
    if os.path.exists(target_file):
        print(f"[{year}] Excel skor already exists. Skipping pre-render on startup.")
        return

    from middleware import helpers_background_task_generate_pre_render_excel
    helpers_background_task_generate_pre_render_excel(year)

@asynccontextmanager
async def app_lifespan(app: FastAPI):
    # Cleanup stale temp files on startup (older than 24h)
    cutoff = time.time() - (24 * 3600)
    for f in os.listdir(TEMP_FOLDER):
        fpath = os.path.join(TEMP_FOLDER, f)
        try:
            if os.path.getmtime(fpath) < cutoff:
                os.remove(fpath)
        except:
            pass

    # Startup Logic
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dbs")
    if os.path.exists(db_path):
        for filename in os.listdir(db_path):
            if filename.startswith("data_") and filename.endswith(".duckdb"):
                year = filename.replace("data_", "").replace(".duckdb", "")
                p = multiprocessing.Process(target=_excel_worker, args=(year,), daemon=True)
                p.start()
    yield # Server runs here
    
    # Shutdown logic (if any) would go here

app = FastAPI(
    docs_url=None, 
    redoc_url=None, 
    openapi_url=None,
    lifespan=app_lifespan
) 

# ==========================================
# MIDDLEWARE SETUP
# ==========================================

# GZIP COMPRESSION (Solves the 100MB issue)
# minimum_size=1000 means responses smaller than 1kb won't be compressed.
app.add_middleware(GZipMiddleware, minimum_size=1000)

# CORS
# CHECK: REMOVE ON PROD;Allow Frontend (8001) to talk to Backend (8000)
# on PROD
# ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:8001,http://localhost:8000").split(",")
# app.add_middleware(
#     CORSMiddleware,
#     # MUST list specific ports. Wildcard "*" will BLOCK cookies.
#     allow_origins=[
#         "http://localhost:8001",
#         "http://127.0.0.1:8001",
#         "http://localhost:8000",
#         "http://127.0.0.1:8000"
#     ],
#     # on PROD
#     # allow_origins=ALLOWED_ORIGINS,
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
#     # Allow JS to read this specific header
#     expose_headers=["X-Total-Count"]
# )

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
        helpers_read_excel_preview,
        helpers_generate_header_mapping,
        helpers_internal_process_temp_file,
        helpers_build_dynamic_query,
        helpers_get_cache_path,
        helpers_get_or_create_intervensi_kegiatan,
        helpers_calculate_dashboard_stats,
        helpers_render_dashboard_html,
        helpers_render_iku_dashboard,
        helpers_generate_excel_workbook,
        helpers_background_task_generate_pre_render_excel,
        ID_COL,
        BASE_DIR as MW_BASE_DIR,
        CONFIG_DIR,
        TEMP_FOLDER as MW_TEMP_FOLDER
    )
except ImportError:
    # Fallback for different context import
    from desa_db.middleware import apply_rekomendasis, make_json_response, helpers_get_db_connection
    from desa_db.middleware import helpers_read_excel_preview, helpers_generate_header_mapping
    from desa_db.middleware import helpers_init_db, helpers_internal_process_temp_file
    from desa_db.middleware import helpers_build_dynamic_query, helpers_get_cache_path
    from desa_db.middleware import helpers_build_dynamic_query, helpers_get_cache_path
    from desa_db.middleware import helpers_generate_excel_workbook
    from desa_db.middleware import helpers_background_task_generate_pre_render_excel
    from desa_db.middleware import ID_COL, BASE_DIR as MW_BASE_DIR, CONFIG_DIR

# ==========================================
# PATH CONFIGURATION (ABSOLUTE PATHS)
# ==========================================

# Get the directory where server.py is located (e.g., C:/.../desa_db)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Temp folder for uploads
TEMP_FOLDER = os.path.join(BASE_DIR, "temp")

# DEFINE TEMPLATE PATHS
# Resolves to: /.../front_end/templates
ROOT_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))
TEMPLATE_DIR = os.path.join(ROOT_DIR, "front_end", "templates")

# Ensure directories exist
os.makedirs(TEMP_FOLDER, exist_ok=True)
os.makedirs(CONFIG_DIR, exist_ok=True)
os.makedirs(TEMPLATE_DIR, exist_ok=True)
os.makedirs(ROOT_DIR, exist_ok=True)

# Pre-compiled exports directory
EXPORT_FOLDER = os.path.abspath(os.path.join(BASE_DIR, "../exports"))
os.makedirs(EXPORT_FOLDER, exist_ok=True)

# Static tailwind css folder
STATIC_DIR = os.path.join(ROOT_DIR, "front_end", "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ==========================================
# Login, logout, 404, Endpoints
# ==========================================
class LoginRequest(BaseModel):
    """Login credentials model."""
    username: str
    password: str

@app.post("/api/login")
async def login(creds: LoginRequest, response: JSONResponse = None):
    """
    Authenticates user and returns JWT in HttpOnly cookie.
    """
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
        max_age=21600,   # 6 hours
        samesite="lax", 
        secure=True      
    )
    return resp

@app.post("/api/logout")
async def logout():
    """
    Clears the session_token HttpOnly cookie.
    """
    resp = JSONResponse(content={"message": "Logged out"})
    resp.delete_cookie(
        key="session_token", 
        httponly=True, 
        samesite="lax", 
        secure=True
    )
    return resp

# 404 handler
@app.exception_handler(404)
async def custom_404_handler(request, exc):
    """
    Returns custom 404.html page instead of JSON error.
    """
    # Returns the HTML page instead of JSON {"detail": "Not Found"}
    return FileResponse(os.path.join(TEMPLATE_DIR, "404.html"), status_code=404)

# LOGIN PAGE (Public)
@app.get("/login", response_class=HTMLResponse)
async def get_login_page():
    """
    Serves the login page (public).
    """
    return FileResponse(os.path.join(TEMPLATE_DIR, "login.html"))

# ADMIN PAGE (Protected)
@app.get("/admin", response_class=HTMLResponse)
async def get_admin_page(request: Request):
    """
    Server-Side Protection:
    Serves admin dashboard page.
    Redirects to /login if no session_token cookie is present.
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
    """
    Redirects root path to /admin.
    """
    return RedirectResponse(url="/admin")

# ==========================================
# API Endpoints
# ==========================================

# Class for Endpoints
# Resumable Uploads Endpoints
class UploadInit(BaseModel):
    """Request model for initializing resumable upload."""
    filename: str
    file_uid: str
    total_size: int
    total_hash: str
class UploadFinalize(BaseModel):
    """Request model for finalizing resumable upload."""
    upload_id: str
    filename: str
    total_hash: str

# Preview Excel Endpoints
class PreviewRequest(BaseModel):
    """Request model for Excel preview."""
    temp_id: str
    filename: str
class HeaderAnalysisRequest(BaseModel):
    """Request model for header mapping analysis."""
    temp_id: str
    filename: str
    header_row_index: int
class ProcessRequest(BaseModel):
    """Request model for final mapped processing step."""
    temp_id: str
    filename: str
    header_row_index: int
    data_start_index: int
    confirmed_mapping: list # List of dicts

# Table Structure Endpoints
@app.get("/config/table_structure", dependencies=[Depends(auth_get_current_user)])
def endpoint_get_table_structure():
    """
    Returns table_structure.csv as JSON for the frontend dashboard.
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
@app.post("/upload/init/{year}", dependencies=[Depends(auth_require_admin)])
async def endpoint_post_upload_init(year: str, payload: UploadInit):
    """
    Initializes resumable upload.
    Checks for existing partial upload and returns current offset.
    """
    # File: server.py (endpoint_post_upload_init)
    # Vulnerability: payload.file_uid is used directly in os.path.join.
    # The Risk: If an attacker sends a file_uid like ../../../../etc/passwd, they could overwrite sensitive system files.
    # Strict validation: Only allow alphanumeric and underscores
    if not re.match(r'^[a-zA-Z0-9_]+$', payload.file_uid):
        return JSONResponse(status_code=400, content={"error": "Invalid upload ID"})

    # Use file_uid (hash+size) to track partial uploads
    temp_file_path = os.path.join(TEMP_FOLDER, f"partial_{payload.file_uid}.tmp")

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
@app.post("/upload/chunk/{year}", dependencies=[Depends(auth_require_admin)])
async def endpoint_post_upload_chunk(
    year: str,
    chunk: UploadFile = File(...),
    upload_id: str = Form(...),
    offset: int = Form(...),
    chunk_hash: str = Form(...)
):
    """
    Receives one chunk of resumable upload.
    MD5 validation + append with explicit f.seek(offset).
    Returns:
        dict: {"status": "ok", "received": int}
    """

    temp_file_path = os.path.join(TEMP_FOLDER, f"partial_{upload_id}.tmp")

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
        f.seek(offset) 
        f.write(content)

    return {"status": "ok", "received": len(content)}

# Resumable Uploads Endpoints
@app.post("/upload/finalize/{year}", dependencies=[Depends(auth_require_admin)])
async def endpoint_post_upload_finalize(year: str, payload: UploadFinalize):
    """
    Finalizes resumable upload after all chunks are received.
    Validates full file MD5 hash, renames to stable temp file, and returns temp_id.
    """
    temp_file_path = os.path.join(TEMP_FOLDER, f"partial_{payload.upload_id}.tmp")

    if not os.path.exists(temp_file_path):
         return JSONResponse(status_code=404, content={"error": "Upload not found"})

    # Validate Total Integrity
    # Note: On very slow CPUs/Large files, this might take a second.
    with open(temp_file_path, "rb") as f:
        final_hash = hashlib.md5(f.read()).hexdigest()

    if final_hash != payload.total_hash:
        return JSONResponse(status_code=400, content={"error": "Final File Corruption (MD5 Mismatch)"})

    # Rename to a stable temp file for the next steps
    temp_id = str(uuid.uuid4())
    # Determine extension
    _, ext = os.path.splitext(payload.filename)
    if not ext: ext = ".xlsb"
    
    safe_temp_path = os.path.join(TEMP_FOLDER, f"raw_{temp_id}{ext}")
    os.rename(temp_file_path, safe_temp_path)

    # Return ID for the frontend to call /preview
    return {
        "status": "uploaded_raw", 
        "temp_id": temp_id, 
        "filename": payload.filename,
        "path_ref": safe_temp_path 
    }

# Upload preview table
@app.post("/upload/preview/{year}", dependencies=[Depends(auth_require_admin)])
async def endpoint_post_upload_preview(year: str, payload: PreviewRequest):
    """
    Returns first 25 rows of the uploaded Excel file for preview and header selection.
    """
    # Reconstruct path based on temp_id
    _, ext = os.path.splitext(payload.filename)
    file_path = os.path.join(TEMP_FOLDER, f"raw_{payload.temp_id}{ext}")
    
    if not os.path.exists(file_path):
        return JSONResponse(status_code=404, content={"error": "Temp file expired or missing"})
        
    try:
        rows = helpers_read_excel_preview(file_path)
        return {"rows": rows}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

# Upload preview Get Header Suggestions
@app.post("/upload/analyze-headers/{year}", dependencies=[Depends(auth_require_admin)])
async def endpoint_post_analyze_headers(year: str, payload: HeaderAnalysisRequest):
    """
    Analyzes the selected header row and returns suggested column mapping
    (first 6 columns by index + fuzzy matching for the rest) and missing headers.
    """
    _, ext = os.path.splitext(payload.filename)
    file_path = os.path.join(TEMP_FOLDER, f"raw_{payload.temp_id}{ext}")
    
    try:
        mapping, missing_headers = helpers_generate_header_mapping(file_path, payload.header_row_index)
        return {"mapping": mapping, "missing_headers": missing_headers}

    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})

# Upload preview Execute Processing with Map
@app.post("/upload/process-mapped/{year}", dependencies=[Depends(auth_require_admin)])
async def endpoint_post_process_mapped(year: str, payload: ProcessRequest):
    """
    Processes the uploaded file using the user-confirmed column mapping.
    Runs full ETL + validation + CDC diff calculation.
    Returns staging result (added/removed/changed counts).
    """
    _, ext = os.path.splitext(payload.filename)
    file_path = os.path.join(TEMP_FOLDER, f"raw_{payload.temp_id}{ext}")
    
    try:
        # Create a new temp ID for the Parquet result
        temp_id = str(uuid.uuid4())
        
        result = helpers_internal_process_temp_file(
            year, 
            file_path, 
            payload.filename, 
            temp_id,
            payload.header_row_index,
            payload.data_start_index,
            payload.confirmed_mapping
        )
        
        # Cleanup Raw File now
        if os.path.exists(file_path): os.remove(file_path)
        
        return result
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})

# Upload or Commit Apply the Staged Changes to update database
@app.post("/commit/{year}", dependencies=[Depends(auth_get_current_user)])
async def endpoint_post_commit_stage(
    year: str,
    background_tasks: BackgroundTasks,
    temp_id: str = Query(...),
    filename: str = Query(...)
    ):
    """
    Commits staged Parquet into SCD Type 2 master_data.
    
    Uses fully parameterized queries:
    - valid_to = ? for expire removed/changed
    - INSERT ... VALUES (?, ?, ?, ?) for new rows + commit log
    - Single transaction + cleanup
    Returns:
        dict: {"status": "success", "message": str} on success
        or JSONResponse 404/500 on error
    """

    if not re.match(r'^[a-zA-Z0-9_-]+$', temp_id):
        return JSONResponse(status_code=400, content={"error": "Invalid temp ID"})

    temp_path = os.path.join(TEMP_FOLDER, f"{temp_id}.parquet")
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
            check_cond = " OR ".join(['(master_data."{col}" IS DISTINCT FROM i."{col}")'.format(col=h.replace('"', '""')) for h in other_cols])

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
            SELECT '{now}', NULL, '{temp_id}', ?, i.* FROM incoming i
            WHERE i."{ID_COL}" NOT IN (
                SELECT "{ID_COL}" FROM master_data WHERE valid_to IS NULL
            )
        """, [filename])

        # Log Commit
        summary = "Update"
        con.execute("INSERT INTO commits VALUES (?, ?, ?, ?)", [temp_id, now, filename, summary])

        con.execute("COMMIT")

        # Trigger background rebuild of the static Excel file
        background_tasks.add_task(helpers_background_task_generate_pre_render_excel, year)

        return {"status": "success", "message": "Database updated successfully."}

    except Exception as e:
        con.execute("ROLLBACK")
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        con.close()
        if os.path.exists(temp_path): os.remove(temp_path)

# Query history changes
@app.get("/query/{year}", dependencies=[Depends(auth_get_current_user)])
def endpoint_get_query_data(
    year: str,
    request: Request,
    limit: int = 1000,
    offset: int = 0,
    filter_col: str = None,
    filter_val: str = None,
    translate: bool = False,
    version: str = None
    ):
    """
    Main data query endpoint with time-travel (SCD Type 2) support.

    Features:
    - Historical snapshot via ?version= timestamp
    - Dynamic filtering from URL params (ILIKE)
    - Optional score → text translation
    - Optimized Polars → JSON streaming + X-Total-Count header
    - Sorting and pagination
    Returns:
        Response: make_json_response (Polars → JSON) with header X-Total-Count
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
        params_dict = dict(request.query_params)
        version = params_dict.get("version")
        base_values = []

        if version:
            # Snapshot Mode: Active at time T
            time_filter = "valid_from <= ? AND (valid_to > ? OR valid_to IS NULL)"
            base_values = [version, version]
        else:
            # HEAD Mode
            time_filter = "valid_to IS NULL"

        base_query = f"SELECT * EXCLUDE (valid_from, valid_to, commit_id) FROM master_data WHERE {time_filter}"

        # Dynamic Filters
        final_query, values = helpers_build_dynamic_query(con, base_query, params_dict, base_values)

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
    Returns commit history and live province → kabupaten → kecamatan hierarchy tree.
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
def endpoint_get_download_server_excel(year: str, request: Request):
    """
    Downloads Excel export (two sheets) for the given year.
    
    Smart logic:
    - If NO filters and NO ?version → serves pre-compiled master file instantly
      (Export_Nasional_{year}_text.xlsx or Export_Nasional_{year}_skor.xlsx)
    - If any filter or ?version is present → builds on-the-fly using helpers_generate_excel_workbook
    
    Features:
    - Full support for translate flag (text vs skor)
    - All dynamic filters and sorting from URL params
    - Time travel via ?version
    - Parameterized query for safety
    
    Sheet 1: Grid Data (full filtered rows)
    Sheet 2: Dashboard Calc (stats + merged headers + rowspans)
    Sheet 3: "Dashboard IKU"
    
    Returns:
        FileResponse: pre-compiled master file (when available)
        or
        StreamingResponse: dynamically generated .xlsx
        (media_type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)
    """
    con, _ = helpers_get_db_connection(year)
    
    try:
        # PREPARE QUERY (Filters + Sort)
        params_dict = dict(request.query_params)
        
        # Check Translate Flag (String "true"/"false" from URL)
        do_translate = params_dict.get("translate", "false").lower() == "true"

        # Time Travel Filter
        version = params_dict.get("version")

        # 1. INTERCEPT: Check if there are any active filters
        valid_cols = [r[0] for r in con.execute("DESCRIBE master_data").fetchall()]
        ignored_keys = {"ids", "version", "limit", "translate", "temp_id", "filename", "sort_by", "sort_dir"}
        
        is_filtered = False
        if params_dict.get("ids"):
            is_filtered = True
        
        for k, v in params_dict.items():
            if k in valid_cols and k not in ignored_keys and v:
                is_filtered = True
                break

        # If NO filters and NO time-travel -> Serve Pre-compiled
        if not is_filtered and not version:
            # Pick the correct file based on frontend UI toggle
            file_suffix = "text" if do_translate else "skor"
            precompiled_path = os.path.join(EXPORT_FOLDER, f"Export_Nasional_{year}_{file_suffix}.xlsx")
            
            if os.path.exists(precompiled_path):
                print(f"[{datetime.now()}] Serving pre-compiled {file_suffix} master excel for {year}")
                return FileResponse(
                    path=precompiled_path,
                    filename=f"Export_Nasional_{file_suffix}_{year}.xlsx",
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

        # 2. DYNAMIC COMPILE: User has active filters, build Excel on the fly
        base_values = []
        if version:
            time_filter = "valid_from <= ? AND (valid_to > ? OR valid_to IS NULL)"
            base_values = [version, version]
        else:
            time_filter = "valid_to IS NULL"
        
        base_query = f"SELECT * EXCLUDE (valid_from, valid_to, commit_id, source_file) FROM master_data WHERE {time_filter}"
        
        # Apply Filters (Provinsi, Kab, Kec, etc.)
        final_query, values = helpers_build_dynamic_query(con, base_query, params_dict, base_values)

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

        # BUILD EXCEL (Using shared helper) - Added params_dict
        wb = helpers_generate_excel_workbook(con, df_grid, do_translate, params_dict)

        # RETURN FILE
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        # Sanitize filename if multiple provinces are selected
        provinsi_val = params_dict.get('Provinsi', 'All')
        if not provinsi_val or provinsi_val == '__NONE__':
            provinsi_val = 'All'
        elif ';' in provinsi_val:
            provinsi_val = 'Multiple_Provinsi'

        filename = f"Export_{provinsi_val}_{year}.xlsx"
        
        # Return as downloadable file (Quotes around filename prevent header injection breaks)
        return StreamingResponse(
            output, 
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )

    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        con.close()

# ==========================================
# CALCULATION & DASHBOARD LOGIC
# ==========================================

# CALCULATION (Rekomendasi ID)
@app.post("/dashboard/calculate/{year}", dependencies=[Depends(auth_get_current_user)])
async def endpoint_post_calculate_dashboard(year: str, request: Request):
    """
    Calculates dashboard statistics on filtered data and returns
    fully rendered HTML table (with proper rowspans) for the frontend.
    Returns:
        HTMLResponse: fully rendered <table> HTML (thead + tbody with rowspans)
    """
    con, _ = helpers_get_db_connection(year)

    try:
        # === Filter DB first (same as /query endpoint) ===
        params_dict = dict(request.query_params)

        # Build base query with time filter
        version = params_dict.get("version")
        base_values = []
        if version:
            time_filter = "valid_from <= ? AND (valid_to > ? OR valid_to IS NULL)"
            base_values = [version, version]
        else:
            time_filter = "valid_to IS NULL"

        base_query = f"SELECT * FROM master_data WHERE {time_filter}"

        # Apply location/id filters (reuse existing helper)
        filtered_query, values = helpers_build_dynamic_query(con, base_query, params_dict, base_values)

        # Execute query to get filtered dataset
        df_filtered = con.execute(filtered_query, values).pl()
        # === End of filtering ===

        # Load CSV Structure
        csv_path = os.path.join(CONFIG_DIR, "table_structure.csv")
        if not os.path.exists(csv_path):
            return HTMLResponse(content="Error: table_structure.csv missing", status_code=404)

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
                "Kode Wilayah Administrasi Desa", "Desa", "Status ID"
            }

            # This list preserves the order of metric columns in the DB
            ordered_db_cols = [r[0] for r in db_cols_info if r[0] not in metadata_cols]
        except:
            return HTMLResponse(content="Error: DB not initialized", status_code=500)

        # Load/Init Templates
        item_names = [row.get("ITEM", "") for row in structure if row.get("ITEM")]
        templates = helpers_get_or_create_intervensi_kegiatan(item_names)

        # Calculate Per Row (Using helpers)
        calculated_rows = helpers_calculate_dashboard_stats(df_filtered, structure, ordered_db_cols, templates)

        # RENDER HTML (NEW HELPER)
        html_table = helpers_render_dashboard_html(calculated_rows)

        # Format for Frontend (Ensure numbers are strings with commas if needed, or send raw)
        # The helper sends raw numbers (Int/Float). 
        # If your frontend expects formatted strings (e.g. "1,024"), convert here or handle in JS.
        # Current frontend code handles raw numbers fine.
        return HTMLResponse(content=html_table)

    except Exception as e:
        traceback.print_exc()
        return HTMLResponse(content=f"Server Error: {str(e)}", status_code=500)
    finally:
        con.close()

# CALCULATION (Dashboard IKU)
@app.post("/dashboard/iku/{year}", dependencies=[Depends(auth_get_current_user)])
async def endpoint_post_calculate_iku_dashboard(year: str, request: Request):
    """
    Calculates and renders the IKU dashboard based on filtered data (Paginated).
    
    Logic:
    - Applies time-travel (?version) and dynamic location/ID filters
    - Fetches filtered DataFrame from master_data
    - Calls helpers_render_iku_dashboard for HTML generation
    
    Returns:
        HTMLResponse: fully rendered <table> HTML (thead + tbody)
    """
    con, _ = helpers_get_db_connection(year)

    try:
        params_dict = dict(request.query_params)
        
        # Pagination Extraction
        limit = int(params_dict.get("limit", 100))
        offset = int(params_dict.get("offset", 0))
        is_append = params_dict.get("is_append", "false").lower() == "true"

        # Build base query with time filter
        version = params_dict.get("version")
        base_values = []
        if version:
            time_filter = "valid_from <= ? AND (valid_to > ? OR valid_to IS NULL)"
            base_values = [version, version]
        else:
            time_filter = "valid_to IS NULL"

        base_query = f"SELECT * FROM master_data WHERE {time_filter}"

        # Apply location/id filters
        filtered_query, values = helpers_build_dynamic_query(con, base_query, params_dict, base_values)

        # Execute query to get filtered dataset
        df_filtered = con.execute(filtered_query, values).pl()

        # Render HTML using the new IKU helper
        # Pass limit, offset, and is_append
        html_table = helpers_render_iku_dashboard(df_filtered, params_dict, limit=limit, offset=offset, is_append=is_append)

        return HTMLResponse(content=html_table)

    except Exception as e:
        traceback.print_exc()
        return HTMLResponse(content=f"Server Error: {str(e)}", status_code=500)
    finally:
        con.close()

# DELETE: Soft Delete (Expire) specific IDs
@app.post("/delete/{year}", dependencies=[Depends(auth_require_admin)])
async def endpoint_post_delete_ids(
    year: str,
    ids: str = Query(..., description="Semicolon or newline separated list of IDs"),
    summary: str = Query("Manual Delete", description="Reason for deletion"),
    # We can inject the user info if we want to log WHO deleted it
    current_user: str = Depends(auth_get_current_user)
    ):
    """
    Soft-deletes records by setting valid_to = NOW().
    Accepts semicolon or newline-separated list of IDs.
    Returns:
        dict: {"status": "success", "deleted_count": int, "deleted_ids": list} or {"status": "warning", "message": str}
        or JSONResponse 400/500 on error
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

        # Vulnerability 1: Soft Delete (server.py) The ids list is pasted directly into the query string using an f-string.
        #     Code: id_sql_list = ", ".join([f"'{x}'" for x in id_list])
        #     Attack: If a user sends an ID like 100' OR '1'='1, the query becomes WHERE ID IN ('100' OR '1'='1'),
        #     potentially deleting all records.
        #     Fix: Use DuckDB's parameter substitution.
        # Vulnerability 2: Time Travel (server.py) The version parameter is injected directly.
        #     Code: f"valid_from <= '{version}' ..."
        #     Attack: ?version=2025-01-01'; DROP TABLE master_data; --
        # Use executing with parameters requires a list of values, not a formatted string.
        # Since IN clauses are hard with parameters, loop or use a temporary table.
        # Better DuckDB approach:
        con.execute("CREATE TEMP TABLE target_ids (id VARCHAR)")
        con.executemany("INSERT INTO target_ids VALUES (?)", [[x] for x in id_list])

        query = f"""
            UPDATE master_data 
            SET valid_to = ?
            WHERE valid_to IS NULL 
            AND "{ID_COL}" IN (SELECT id FROM target_ids)
            RETURNING "{ID_COL}"
        """ 

        # Execute and fetch the IDs that were actually updated
        deleted_rows = con.execute(query, [now]).fetchall()
        changes = len(deleted_rows)

        if changes > 0:
            # Log the Commit (using uuid for consistency)
            commit_id = str(uuid.uuid4())
            con.execute("INSERT INTO commits VALUES (?, ?, 'Manual Delete', ?)", [commit_id, now, f"{summary} ({changes} rows)"])
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
    Git-style diff for a commit (valid_from = ? / valid_to = ?).
    Returns:
        JSONResponse: {"changes": list[dict]} with type ADD/MOD/DEL/INFO
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
