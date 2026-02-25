import os
import json
import re
import duckdb
import html as h
import polars as pl
import openpyxl
from difflib import SequenceMatcher
from fastapi import Response
from fastapi.responses import JSONResponse

# ==========================================
# CONFIGURATION
# ==========================================
# /root
#   /root
#   /.config/headers.json
#   /.config/intervensi_kegiatan.json
#   /.config/rekomendasi.json
#   /.config/table_structure.csv
#   /desa_db/server.py
#   /desa_db/middleware.py
#   /front_end/router.py
#   /front_end/templates/admin.html
#   /front_end/templates/user.html
#   /front_end/templates/login.html


# Resolves to: /.../desa_db
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Resolves to: /.../.config
CONFIG_DIR = os.path.abspath(os.path.join(BASE_DIR, "../.config"))

# Resolves to: /.../desa_db/dbs
DB_FOLDER = os.path.join(BASE_DIR, "dbs")

# Resolves to: /.../desa_db/staging
STAGING_FOLDER = os.path.join(BASE_DIR, "staging")

# Config Files
JSON_PATH = os.path.join(CONFIG_DIR, "rekomendasi.json")

# intervensi_kegiatan files
INTERVENTION_FILE = os.path.join(CONFIG_DIR, "intervensi_kegiatan.json")

# Header File: inside .config/headers.json (sibling of desa_db)
HEADER_FILE = os.path.join(CONFIG_DIR, "headers.json")

# Data Structure Constants
# ID_COL acts as the Primary Key for deduplication and version control.
ID_COL = "Kode Wilayah Administrasi Desa" 


# Point to ../.config/rekomendasi.json relative to this file
os.makedirs(DB_FOLDER, exist_ok=True)

# ==========================================
# LOGIC LOADER (Existing)
# ==========================================
def load_logic():
    """
    Loads rekomendasi.json and converts string keys ("1", "2", ...) to integers.
    Returns empty dict if file is missing (safe fallback).
    """
    if not os.path.exists(JSON_PATH):
        # Fallback: Return empty dict if file is missing (prevents crashes)
        return {}

    with open(JSON_PATH, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    # CRITICAL STEP: Convert JSON String keys ("1") to Integers (1)
    # If we don't do this, Polars won't match the Integer data in DB.
    clean_logic = {}
    for col_name, mapping in raw_data.items():
        # Convert keys to int, keep values as is
        clean_logic[col_name] = {int(k): v for k, v in mapping.items()}

    return clean_logic

# Load once on startup
RECOMMENDATION_LOGIC = load_logic()

# ==========================================
# OPTIMIZED BATCH EXECUTION
# ==========================================
def apply_rekomendasis(df: pl.DataFrame) -> pl.DataFrame:
    """
    Applies all recommendation rules from RECOMMENDATION_LOGIC in a single batch pass.
    Uses replace_strict for Polars 1.0+ compatibility and optimal performance.
    Only processes columns that exist in the DataFrame.
    """
    exprs = []

    # Build the list of instructions (Lazy Evaluation)
    for col_name, logic_map in RECOMMENDATION_LOGIC.items():
        if col_name in df.columns:
            expr = (
                pl.col(col_name)
                # OPTIMIZATION: Data is already Int from DB.
                # This explicitly handles the 'default' and 'return_dtype' logic
                .replace_strict(logic_map, default=None, return_dtype=pl.String)
                .alias(col_name)
            )
            exprs.append(expr)

    # Execute all instructions at once
    if exprs:
        return df.with_columns(exprs)

    return df

def make_json_response(df: pl.DataFrame) -> Response:
    """
    OPTIMIZATION: 
    Converts Polars DataFrame directly to JSON string using Rust engine
    and returns a FastAPI Response. Bypasses Python's slow list-of-dicts conversion
    for better performance on large datasets.
    """
    # Serialize directly to JSON string using Rust engine
    json_str = df.write_json()

    # Return direct Response (skips FastAPI's jsonable_encoder overhead)
    return Response(content=json_str, media_type="application/json")

# ==========================================
# DATABASE HELPERS
# ==========================================

# PREVIEW & MAPPING HELPERS, sends back to frontend for user to check headers
def helpers_read_excel_preview(file_path: str, limit_rows: int = 25):
    """
    Reads first N rows of 'Skor' sheet for frontend preview.
    - .xlsx: openpyxl streaming (read_only=True) for low memory
    - .xlsb/.xlsx fallback: Polars calamine
    - Caps at 263 columns
    - Converts None → ""
    - Returns pure list-of-lists
    Returns:
        list[list[str]]: rows as list of lists (max limit_rows rows, 263 cols)
    """
    rows = []

    try:
        # OPTIMIZATION: Streaming for .xlsx
        if file_path.lower().endswith(".xlsx"):
            # read_only=True ensures we don't load the whole file
            wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
            
            # Handle Sheet Selection
            if "Skor" in wb.sheetnames:
                ws = wb["Skor"]
            else:
                ws = wb.active

            # Iterate only the rows we need
            # fetch limit_rows + 5 just in case some are empty, but typically exact limit is fine
            for row in ws.iter_rows(min_row=1, max_row=limit_rows, values_only=True):
                # Convert None to "" and map to list
                clean_row = [str(cell) if cell is not None else "" for cell in row]
                
                # Check if row has data
                rows.append(clean_row[:263])

            wb.close()
            return rows

        # Read without headers to get raw grid
        else:
            df = pl.read_excel(
                file_path,
                sheet_name="Skor",
                engine="calamine",
                has_header=False # Direct argument, not inside dict
            )
            
            # Slice row limit manually
            df = df.head(limit_rows)

            # Limit width (similar to existing logic)
            max_col = min(df.width, 263)
            df = df[:, :max_col]
            
            # Replace nulls with empty string for JSON safety
            data = df.fill_null("").to_dicts()
            
            # Convert to list of lists (easier for generic grid in JS)
            # Polars to_dicts returns list of objects with "column_0", "column_1", etc.
            # Only pure values.
            rows = [list(row.values()) for row in data]
            return rows

    except Exception as e:
        raise Exception(f"Preview Error: {str(e)}")

def helpers_normalize_text(text: str):
    """
    Normalizes text for fuzzy header matching:
    - Lowercase
    - Remove quotes
    - Collapse multiple whitespace
    - Strip
    """
    if not text: return ""
    text = str(text).lower()
    text = re.sub(r'["\']', '', text) # Remove quotes
    text = re.sub(r'\s+', ' ', text)  # Collapse spaces
    return text.strip()

def helpers_generate_header_mapping(file_path: str, header_row_idx: int):
    """
    Generates column mapping from uploaded Excel against headers.json.

    Logic:
    - Detects first non-empty column → start_col (dynamic alignment)
    - First 6 columns: forced index mapping + auto-confirm
    - Remaining columns: alias_exact (from headers.json "aliases") or fuzzy SequenceMatcher
      - > 85% → auto-confirm
      - < 40% → "(No Match)"
    - .xlsx: streams only the header row with openpyxl
    - Skips empty columns
    Returns:
        list[dict]: mapping entries with keys: standard, file_header, col_index, is_confirmed, match_type, score
    """

    # Load Standard Headers
    if not os.path.exists(HEADER_FILE):
        raise Exception("Configuration file not found: headers.json")

    with open(HEADER_FILE, "r", encoding="utf-8") as f:
        headers_data = json.load(f)
        standard_headers = [item["standard"] for item in headers_data]

    file_headers_raw = []

    # OPTIMIZATION: Streaming for .xlsx
    if file_path.lower().endswith(".xlsx"):
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        if "Skor" in wb.sheetnames:
            ws = wb["Skor"]
        else:
            ws = wb.active
        
        # OpenPyXL is 1-based, header_row_idx is 0-based.
        target_excel_row = header_row_idx + 1
        
        # Iterate until we hit the row (efficient skipping)
        for i, row in enumerate(ws.iter_rows(min_row=target_excel_row, max_row=target_excel_row, values_only=True)):
            clean_row = [str(cell) if cell is not None else "" for cell in row]
            file_headers_raw = clean_row[:263]
            break
        
        wb.close()
        
        if not file_headers_raw:
             raise Exception(f"Header row index {header_row_idx} is out of bounds or empty.")
             
    else:
        # Fallback for .xlsb
        df = pl.read_excel(
            file_path,
            sheet_name="Skor",
            engine="calamine",
            has_header=False
        )
        max_col = min(df.width, 263)
        df = df[:, :max_col]

        if header_row_idx >= df.height:
            raise Exception(f"Header row index {header_row_idx} is out of bounds")

        # Get the raw list of values from the target row
        # Polars reads as col_0, col_1.
        file_headers_raw = list(df.row(header_row_idx))
    
    mapping = []
    special_first_6 = standard_headers[:6]
    remaining_standards = standard_headers[6:]
    
    # DYNAMIC ALIGNMENT: Find the first non-empty column in the Excel file.
    # This prevents assigning "Provinsi" to an empty Column A.
    start_col = 0
    for i, val in enumerate(file_headers_raw):
        if val.strip() != "":
            start_col = i
            break

    # Map Special First 6 using the actual start column
    for i in range(min(6, len(file_headers_raw) - start_col)):
        if start_col + i >= len(file_headers_raw):
            break
        file_val = str(file_headers_raw[start_col + i]).strip()
        std_val = special_first_6[i]
        
        # Auto-confirm the first 6 based on User's rule "the order always right"
        mapping.append({
            "standard": std_val,
            "file_header": file_val,
            "col_index": start_col + i,
            "is_confirmed": True, 
            "match_type": "index_forced"
        })

    # --- LOGIC: REMAINING COLUMNS (Fuzzy Name Match) ---
    # Create a lookup for normalized standard headers
    # use a list of tuples to keep order: [(norm, original), ...]
    norm_standards = [(helpers_normalize_text(h), h) for h in remaining_standards]
    
    # Resume fuzzy mapping after the first 6
    fuzzy_start_idx = start_col + 6
    for i in range(fuzzy_start_idx, len(file_headers_raw)):
        file_val = str(file_headers_raw[i]).strip()

        # Even if empty, we list it so user can see it (but usually ignore)
        if not file_val: continue # Skip empty columns
        
        # SKIP EMPTY COLUMNS
        # If the header in the file is empty/None/NaN, it's not a valid data column.
        # Don't even try to map it.
        if not file_val or file_val.lower() == "none" or file_val == "":
            continue

        norm_file = helpers_normalize_text(file_val)
        best_match = None
        highest_ratio = 0.0
        is_match = False
        match_type = "fuzzy"

        # Match based on headers.json and it's aliases
        for item in headers_data[6:]: 
            original_std = item["standard"]
            valid_names = [helpers_normalize_text(a) for a in item.get("aliases", [])]
            valid_names.append(helpers_normalize_text(original_std)) 

            if norm_file in valid_names:
                best_match = original_std
                highest_ratio = 1.0
                is_match = True
                match_type = "alias_exact"
                break

        if not best_match:
            # Find best match in remaining standards
            for norm_std, orig_std in norm_standards:
                # Exact match (normalized)
                if norm_std == norm_file:
                    best_match = orig_std
                    highest_ratio = 1.0
                    is_match = True
                    match_type = "fuzzy_exact"
                    break
            
                # Fuzzy match (Levenshtein) using python's difflib
                ratio = SequenceMatcher(None, norm_std, norm_file).ratio()
                if ratio > highest_ratio:
                    highest_ratio = ratio
                    best_match = orig_std

            # If the best match is less than 40%, it's likely garbage.
            if highest_ratio < 0.4:
                best_match = None

            # Threshold for "Auto Confirm" (e.g., 85% similarity)
            # "Apakah ..." vs "Apakah ...?" usually > 0.95
            # Display all, BUT auto-confirm only if > 85%
            is_match = highest_ratio > 0.85
        
        # If no match found above 0, just leave standard empty or guess best
        mapping.append({
            "standard": best_match if best_match else "(No Match)",
            "file_header": file_val,
            "col_index": i,
            "is_confirmed": is_match,
            "match_type": match_type,
            "score": round(highest_ratio, 2)
        })

    return mapping

# PROCESSOR to rebould db based on headers.json
def helpers_sync_db_schema(con: duckdb.DuckDBPyConnection, year: str):
    """
    Synchronizes master_data table schema with headers.json.
    Adds any missing columns (VARCHAR for text columns, TINYINT for scores).
    """
    if not os.path.exists(HEADER_FILE): return

    with open(HEADER_FILE, "r", encoding="utf-8") as f:
        headers_data = json.load(f)
        target_headers = [item["standard"] for item in headers_data]

    # Get existing DB columns
    existing_cols = set([r[0] for r in con.execute("DESCRIBE master_data").fetchall()])
    
    TEXT_COLUMNS = {
        "Provinsi", "Kabupaten/ Kota", "Kecamatan", 
        "Kode Wilayah Administrasi Desa", "Desa", "Status ID"
    }

    for h in target_headers:
        # If header contains quotes, strip them for comparison
        clean_h = h.replace('"', '')
        if clean_h not in existing_cols:
            print(f"Schema Evolution: Adding column '{clean_h}' to {year}...")
            # Determine Type
            dtype = "VARCHAR" if clean_h in TEXT_COLUMNS else "TINYINT"
            try:
                con.execute(f'ALTER TABLE master_data ADD COLUMN "{clean_h}" {dtype}')
            except Exception as e:
                print(f"Failed to add column {clean_h}: {e}")

# INTERNAL FILE PROCESSOR, staging uploads basically
def helpers_internal_process_staging_file(
    year: str,
    file_path: str,
    filename: str,
    staging_id: str,
    header_row_idx: int,
    data_start_idx: int,
    confirmed_mapping: list
    ):
    """
    Full ETL processor for staging upload.
    
    Alignment fixes:
    - openpyxl scan: counts leading empty rows + first non-empty column offset
    - calamine read (has_header=False) then applies row/col offsets
    - Duplicate column resolution: prefers column with highest numeric values
    
    Processing steps:
    - Row slice after offset
    - Confirmed mapping only (renames to standard names)
    - Drop fully null/empty columns
    - Strict Status ID validation
    - Filter 10-digit IDs
    - Cast: text columns → String, scores → Int8 (strict=False)
    - Write {staging_id}.parquet
    - CDC diff vs current master_data (valid_to IS NULL)
    Returns:
        dict: {"status": "staged", "staging_id": str, "filename": str, "diff": {"added": int, "removed": int, "changed": int, "total_incoming": int}}
    """

    try:

        # --- ETL: Extraction & Cleaning (Polars) ---
        print(f"Processing {filename} for year {year}...")

        # ALIGNMENT FIX: Count ALL empty rows up to the user's selected start index.
        # This perfectly syncs the frontend openpyxl index with the backend Calamine index
        # regardless of how many empty rows exist between headers and data.
        calamine_row_offset = 0
        calamine_col_offset = 0
        
        if file_path.lower().endswith(".xlsx"):
            try:
                wb_check = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
                ws_check = wb_check["Skor"] if "Skor" in wb_check.sheetnames else wb_check.active
                
                empty_rows_count = 0
                min_col = 9999
                
                # Check up to data_start_idx to count every empty row Calamine might drop
                for r_idx, row in enumerate(ws_check.iter_rows(min_row=1, max_row=data_start_idx + 1, values_only=True)):
                    row_has_data = False
                    for c_idx, cell in enumerate(row):
                        if cell is not None and str(cell).strip() != "":
                            row_has_data = True
                            if c_idx < min_col:
                                min_col = c_idx
                    
                    if not row_has_data:
                        empty_rows_count += 1
                
                calamine_row_offset = empty_rows_count
                calamine_col_offset = min_col if min_col != 9999 else 0
                wb_check.close()
            except Exception as e:
                print(f"Warning calculating offset: {e}")

        # Read .xlsb/.xlsx using 'calamine'
        df = pl.read_excel(
            file_path,
            sheet_name="Skor",
            engine="calamine",
            has_header=False # Direct argument, not inside dict
        )
        print(f"1. Initial read: {df.height} rows (Empty rows stripped: {calamine_row_offset}, Col Offset: {calamine_col_offset})", flush=True)

        # Structure Cleaning:
        # Slice: Cap width to prevent reading infinite empty Excel columns
        max_col = min(df.width, 263) 
        df = df[:, :max_col] # DO NOT drop columns manually anymore; Calamine offset handles it safely

        # Sync the absolute UI index with Calamine's stripped index
        adjusted_data_start = max(0, data_start_idx - calamine_row_offset)

        # Slice Rows (Data Start)
        # Assume data_start_idx is the 0-based index from the file where actual data begins.
        # Example: Header at 3, Data at 4.
        # df[4] is the first data row.
        if adjusted_data_start < df.height:
            df = df.slice(adjusted_data_start, None)
            print(f"2. After row slice (UI start={data_start_idx}, Adjusted={adjusted_data_start}): {df.height} rows", flush=True)
        else:
             raise Exception(f"Data start index {data_start_idx} is out of bounds")

        # Apply Column Mapping
        target_to_cols = {}
        for m in confirmed_mapping:
            if m.get('is_confirmed'):
                t = m['standard']
                if t not in target_to_cols:
                    target_to_cols[t] = []

                # Adjust absolute UI index to relative Calamine index
                cal_idx = m['col_index'] - calamine_col_offset
                if cal_idx >= 0:
                    target_to_cols[t].append(cal_idx)

        selection_exprs = []
        for target_name, indices in target_to_cols.items():
            if not indices:
                continue
                
            chosen_idx = indices[0]

            # Resolve duplicates by checking if the dataframe column contains numbers
            if len(indices) > 1:
                for idx in indices:
                    if idx < df.width:
                        col_name = df.columns[idx]
                        # Cast to Int8 (strict=False turns text/invalid data to null). 
                        # If it has valid numbers, it is the correct score column.
                        numeric_count = df[col_name].cast(pl.Int8, strict=False).is_not_null().sum()
                        if numeric_count > 0:
                            chosen_idx = idx
                            break 

            if 0 <= chosen_idx < df.width:
                original_name = df.columns[chosen_idx]
                selection_exprs.append(pl.col(original_name).alias(target_name))

        if not selection_exprs:
            raise Exception("No columns were confirmed for mapping.")

        df = df.select(selection_exprs)
        print(f"3. After column mapping: {df.height} rows", flush=True)
        if ID_COL in df.columns:
            print(f" -> Sample data in ID_COL: {df[ID_COL].head(3).to_list()}", flush=True)

        # Filter: Remove columns that are entirely Empty or Null
        df = df.select([
            col for col in df 
            if not (col.is_null().all() or (col.dtype == pl.String and (col == "").all()))
        ])
        print(f"4. After dropping empty cols: {df.height} rows", flush=True)

        # VALIDATION: Status ID (Strict)
        if "Status ID" in df.columns:
            valid_statuses = ["BERKEMBANG", "MAJU", "MANDIRI", "SANGAT TERTINGGAL", "TERTINGGAL"]
            
            # Check for invalid values
            # is_in returns boolean series. ~ negates it.
            invalid_rows = df.filter(
                ~pl.col("Status ID").str.to_uppercase().is_in(valid_statuses) 
                & pl.col("Status ID").is_not_null() 
                & (pl.col("Status ID") != "")
            )
            
            if invalid_rows.height > 0:
                bad_vals = invalid_rows["Status ID"].unique().to_list()
                raise Exception(f"Invalid 'Status ID' found: {bad_vals}. Allowed: {valid_statuses}")

        # Filter: Keep only rows where at least one column looks like an ID
        # Pattern: 10 digits (Standard Indonesian Region Code)
        if ID_COL in df.columns:
            pattern = r"[0-9]{10}"
            match_count = df.filter(pl.col(ID_COL).cast(pl.String).str.contains(pattern)).height
            print(f"5. Rows matching exactly 10 digits: {match_count}", flush=True)
            
            df = df.filter(
                pl.col(ID_COL).cast(pl.String).str.contains(pattern)
            )
            print(f"6. After ID filter: {df.height} rows", flush=True)

        # OPTIMIZATION Type Casting (Optimized)
        # Identify Text Columns (same as middleware)
        TEXT_COLUMNS = {
            "Provinsi", "Kabupaten/ Kota", "Kecamatan", 
            "Kode Wilayah Administrasi Desa", "Desa", "Status ID"
        }

        # Cast, if non TEXT_COLUMNS return int8 (TINYINT)
        exprs = []
        for col in df.columns:
            if col in TEXT_COLUMNS:
                exprs.append(pl.col(col).cast(pl.String))
            else:
                exprs.append(pl.col(col).cast(pl.Int8, strict=False))
        
        df = df.with_columns(exprs)

        # Save Staged Data (Parquet will now store these as Integers)
        final_parquet_path = os.path.join(STAGING_FOLDER, f"{staging_id}.parquet")
        df.write_parquet(final_parquet_path)

        # Uncomment for the debug to activate. what this debug does is to check what's inside
        # the excel files
        # print(f"\n--- DEBUG LOG FOR {filename} ---", flush=True)
        # print(f"Total rows remaining after Polars cleaning: {df.height}", flush=True)
        # 
        # if ID_COL in df.columns:
        #     sample_ids = df[ID_COL].head(20).to_list()
        #     print(f"Sample IDs (First 20): {sample_ids}", flush=True)
        # else:
        #     print(f"CRITICAL WARNING: Column '{ID_COL}' is MISSING!", flush=True)
        # print("--------------------------------\n", flush=True)

        # Compare with DB (CDC Logic - Identical to previous)
        con, db_path = helpers_get_db_connection(year)
        helpers_init_db(con, df.columns) # Ensure tables exist
        helpers_sync_db_schema(con, year) # Check headers.json vs DB

        # Identify Incoming Data
        con.execute(f"CREATE OR REPLACE TEMP TABLE incoming AS SELECT * FROM read_parquet('{final_parquet_path}')")
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
            check_conditions = " OR ".join(['(c."{col}" IS DISTINCT FROM i."{col}")'.format(col=h.replace('"', '""')) for h in other_cols])
            changed_count = con.execute(f"""
                SELECT COUNT(*) FROM current_state c
                JOIN incoming i ON c."{ID_COL}" = i."{ID_COL}"
                WHERE {check_conditions}
            """).fetchone()[0]

        con.close()

        return {
            "status": "staged",
            "staging_id": staging_id,
            "filename": filename,
            "diff": {
                "added": added_count,
                "removed": removed_count,
                "changed": changed_count,
                "total_incoming": df.height
            }
        }
    except Exception as e:
        raise e

def helpers_get_db_connection(year: str):
    """
    Returns DuckDB connection and path for the given year.
    Validates year format (must be 20XX).
    """
    clean_year = os.path.basename(year)

    if not re.match(r'^20\d{2}$', clean_year):
        raise ValueError(f"Year must start with 20XX, got: '{clean_year}'")

    db_path = os.path.join(DB_FOLDER, f"data_{clean_year}.duckdb")
    con = duckdb.connect(db_path)
    return con, db_path

def helpers_get_cache_path(year: str):
    """
    Returns the absolute path to the unique_cache JSON file for a specific year.
    """
    get_cache_path_clean_year = os.path.basename(year)
    return os.path.join(CONFIG_DIR, f"unique_cache_{get_cache_path_clean_year}.json")

def helpers_init_db(con: duckdb.DuckDBPyConnection, headers: list[str]):
    """
    SCD Type 2 Schema:

    Initializes SCD Type 2 schema for master_data and commits tables.
    - Creates tables if they don't exist
    - Uses TINYINT for score columns, VARCHAR for text/metadata
    - Adds index on ID_COL
    """
    # Construct column definitions for SQL (e.g., "Col1" VARCHAR, "Col2" VARCHAR...)
    # Note: Wrap headers in double quotes to handle spaces or special chars in column names.

    # define columns that MUST remain text/string
    TEXT_COLUMNS = {
        "valid_from", "valid_to", "commit_id", "source_file",
        "Provinsi", "Kabupaten/ Kota", "Kecamatan", 
        "Kode Wilayah Administrasi Desa", "Desa", "Status ID"
    }

    cols_def = []
    for h in headers:
        if h in TEXT_COLUMNS:
            cols_def.append(f'"{h}" VARCHAR')
        else:
            # OPTIMIZATION: Use TINYINT for 1-5 scores
            cols_def.append(f'"{h}" TINYINT')

    cols_optimized = ", ".join(cols_def)

    # Create the MAIN table (Latest Snapshot)
    # Includes metadata: 'last_updated' and 'source_file'
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS master_data (
            valid_from TIMESTAMP,
            valid_to TIMESTAMP,
            commit_id VARCHAR,
            source_file VARCHAR,
            {cols_optimized}
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

def helpers_build_dynamic_query(con, base_query, request_params, base_values=None):
    """
    Builds parameterized WHERE clause from query params.
    Supports:
    - ids (semicolon/newline separated) → IN (?)
    - column ILIKE ? for any valid column
    - Prepends base_values (e.g. for time-travel ?version)
    Returns:
        tuple[str, list]: (final_query_with_where, values_list_for_execution)
    """
    # Get valid column names from the 'master_data' table to prevent SQL injection
    valid_cols = [r[0] for r in con.execute("DESCRIBE master_data").fetchall()]

    filters = []
    values = base_values[:] if base_values else []

    # Iterate over all query parameters
    # A. SPECIAL FILTER: ID List (Comma Separated)
    if "ids" in request_params and request_params["ids"]:
        raw_ids = request_params["ids"]

        # STRICT RULE: Split by SEMICOLON (;) or Newline. NO COMMAS.
        filtered_ids = re.split(r'[;\n\r]+', raw_ids)

        # Strip each token and remove empty strings in one pass
        id_list = [x.strip() for x in filtered_ids if x.strip()]

        if id_list:
            # Create placeholders (?, ?, ?)
            placeholders = ", ".join(["?"] * len(id_list))
            filters.append(f'"{ID_COL}" IN ({placeholders})')
            values.extend(id_list)

    # B. STANDARD FILTERS
    ignored_keys = ["ids", "version", "limit", "translate", "staging_id", "filename", "sort_by", "sort_dir"]
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

def helpers_get_or_create_intervensi_kegiatan(items: list[str]):
    """
    Loads or creates intervensi_kegiatan.json.
    If file doesn't exist, generates default templates based on rekomendasi.json (when available).
    """
    # Try Load
    if os.path.exists(INTERVENTION_FILE):
        try:
            with open(INTERVENTION_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass # Fallback if corrupt

    # Create Defaults (using rekomendasi.json logic if available, else generic)
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
            # this below is when rekomendasi.json isn't filled
            defaults[item] = {
                "1": f"Perlu peningkatan {item} (Sangat Kurang)",
                "2": f"Perlu peningkatan {item} (Kurang)",
                "3": f"Perlu peningkatan {item} (Cukup)",
                "4": f"Perlu peningkatan {item} (Baik)",
                "5": None
            }

    # Save to Disk
    try:
        with open(INTERVENTION_FILE, "w", encoding="utf-8") as f:
            json.dump(defaults, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ Could not save intervensi_kegiatan: {e}")

    return defaults

# reusable dashboard calculate
def helpers_calculate_dashboard_stats(df_data, structure, ordered_db_cols, templates):
    """
    Calculates dashboard statistics (average score, count per score level, and intervention narrative)
    for each row in table_structure.csv using the provided DataFrame.
    Shared logic used by both UI rendering and Excel export.
    """
    calculated_rows = []

    for idx, row in enumerate(structure):
        # Default Empty Stats
        stats = {
            "SKOR Rata-Rata": "",
            "SKOR 1": "", "SKOR 2": "", "SKOR 3": "", "SKOR 4": "", "SKOR 5": "",
            "INTERVENSI KEGIATAN": ""
        }

        # Calculation Logic (Match CSV Row Index -> DB Column Index)
        if idx < len(ordered_db_cols):
            target_col = ordered_db_cols[idx]

            if target_col in df_data.columns:
                try:
                    # Select specific column as Series
                    s = df_data.select(pl.col(target_col).cast(pl.Int64, strict=False)).to_series()
                    
                    avg = s.mean()
                    c1 = (s == 1).sum()
                    c2 = (s == 2).sum()
                    c3 = (s == 3).sum()
                    c4 = (s == 4).sum()
                    c5 = (s == 5).sum()

                    if avg is not None: 
                        stats["SKOR Rata-Rata"] = round(avg, 2)
                    if c1: stats["SKOR 1"] = c1
                    if c2: stats["SKOR 2"] = c2
                    if c3: stats["SKOR 3"] = c3
                    if c4: stats["SKOR 4"] = c4
                    if c5: stats["SKOR 5"] = c5

                    # Narrative Generation
                    narrative_parts = []
                    t_map = templates.get(row.get("ITEM", ""), {})
                    cnt_map = {1: c1, 2: c2, 3: c3, 4: c4, 5: c5}
                    
                    for score in [1, 2, 3, 4, 5]:
                        if cnt_map[score] > 0 and t_map.get(str(score)):
                            # Format number with commas for text
                            narrative_parts.append(f"{cnt_map[score]:,} {t_map[str(score)]}")
                    
                    if narrative_parts:
                        stats["INTERVENSI KEGIATAN"] = "\n".join(narrative_parts)

                except Exception as e:
                    print(f"Calc error on column {target_col}: {e}")

        # Merge Stats into the Original Row
        # This ensures we have the metadata (NO, DIMENSI...) + The Calculated Stats + The Pelaksana info
        row.update(stats)
        calculated_rows.append(row)

    return calculated_rows

# rendering dashboard
# the logic for rendering moved here, reason so no one can inspect the logic on <script>
def helpers_render_dashboard_html(calculated_rows: list[dict]) -> str:
    """
    Server-side HTML renderer for the dashboard table.
    - Builds full <thead> + <tbody> with proper rowspans for merged columns (NO, DIMENSI, SUB DIMENSI, INDIKATOR)
    - Escapes content to prevent XSS
    - Adds data-col-idx and resizer elements for frontend features (freeze, resize)
    """
    if not calculated_rows:
        return "<tbody><tr><td colspan='17' class='text-center p-4'>No Data</td></tr></tbody>"

    # Define Column Indices mapping to ensure alignment between Header and Body
    # 0:NO, 1:DIM, 2:SUB, 3:IND, 4:ITEM, 5-10:SKOR, 11:INTERVENSI, 12-16:PELAKSANA
    
    # --- BUILD HEADER (Static Structure based on your CSV layout) ---
    #add 'data-col-idx' and the 'resizer' div.
    html = """
    <thead>
        <tr>
            <th class="col-no relative" rowspan="2" data-col-idx="0"><span>NO</span><div class="resizer"></div></th>
            <th class="col-dimensi relative" rowspan="2" data-col-idx="1"><span>DIMENSI</span><div class="resizer"></div></th>
            <th class="col-sub_dimensi relative" rowspan="2" data-col-idx="2"><span>SUB DIMENSI</span><div class="resizer"></div></th>
            <th class="col-indikator relative" rowspan="2" data-col-idx="3"><span>INDIKATOR</span><div class="resizer"></div></th>
            <th class="col-item relative" rowspan="2" data-col-idx="4"><span>ITEM</span><div class="resizer"></div></th>
            <th colspan="6">SKOR</th>
            <th class="col-intervensi relative" rowspan="2" data-col-idx="11">INTERVENSI<div class="resizer"></div></th>
            <th colspan="5">PELAKSANA</th>
        </tr>
        <tr>
            <th class="col-score relative" data-col-idx="5">Rata<div class="resizer"></div></th>
            <th class="col-score relative" data-col-idx="6">1<div class="resizer"></div></th>
            <th class="col-score relative" data-col-idx="7">2<div class="resizer"></div></th>
            <th class="col-score relative" data-col-idx="8">3<div class="resizer"></div></th>
            <th class="col-score relative" data-col-idx="9">4<div class="resizer"></div></th>
            <th class="col-score relative" data-col-idx="10">5<div class="resizer"></div></th>
            <th class="col-pusat relative" data-col-idx="12">PUSAT<div class="resizer"></div></th>
            <th class="col-prov relative" data-col-idx="13">PROV<div class="resizer"></div></th>
            <th class="col-kab relative" data-col-idx="14">KAB<div class="resizer"></div></th>
            <th class="col-desa relative" data-col-idx="15">DESA<div class="resizer"></div></th>
            <th class="col-lain relative" data-col-idx="16">LAIN<div class="resizer"></div></th>
        </tr>
    </thead>
    <tbody>
    """

    # --- CALCULATE ROW SPANS (Ported from JS) ---
    # pre-calculate spans to know when to output <td rowspan="X"> or skip
    n_rows = len(calculated_rows)
    row_spans = [{"NO": 0, "DIMENSI": 0, "SUB DIMENSI": 0, "INDIKATOR": 0} for _ in range(n_rows)]
    merge_keys = ["NO", "DIMENSI", "SUB DIMENSI", "INDIKATOR"]

    # Map keys to their CSS classes
    col_css_map = {
        "NO": "col-no",
        "DIMENSI": "col-dimensi",
        "SUB DIMENSI": "col-sub_dimensi",
        "INDIKATOR": "col-indikator"
    }

    for k in merge_keys:
        i = 0
        while i < n_rows:
            # Start of a potential span
            span = 1
            j = i + 1
            while j < n_rows:
                # Check if current row matches start row
                if calculated_rows[i].get(k) == calculated_rows[j].get(k):
                    # (e.g., Can't merge "SUB DIMENSI A" if "DIMENSI" changed)
                    parents_match = True
                    idx_k = merge_keys.index(k)
                    for p_idx in range(idx_k): # Check all keys before current K
                        p_key = merge_keys[p_idx]
                        if calculated_rows[i].get(p_key) != calculated_rows[j].get(p_key):
                            parents_match = False
                            break
                    
                    if parents_match:
                        span += 1
                        row_spans[j][k] = -1 # Mark as "skip"
                        j += 1
                    else:
                        break
                else:
                    break
            
            row_spans[i][k] = span
            i = j # Jump forward

    # --- BUILD BODY HTML ---
    for i, row in enumerate(calculated_rows):
        html += "<tr>"
        
        # Helper
        def make_td(content, idx, css_class="", rowspan=1, is_merged=False):
            # Combine passed class with merged-cell class
            cls = f"{css_class} {'merged-cell' if is_merged else ''}".strip()
            
            # Default padding is 6px, but 'col-no' has !important padding:0 in CSS
            # add vertical-align: top to everything.
            style = "vertical-align: top;"
            
            # Only add whitespace wrap if it's NOT the NO column (which is centered/tight)
            if "col-no" not in css_class:
                style += " white-space: pre-wrap; padding: 6px;"
            
            # File: middleware.py (Function: helpers_render_dashboard_html)
            # Vulnerability: You use f-strings to build HTML: f'>{content or ""}</td>'.
            # The Risk: If an attacker uploads an Excel file where the "Desa" column contains <script>alert('Hacked')</script>,
            # that script will execute in the browser of every admin who views the dashboard.
            safe_content = h.escape(str(content)) if content else ""
            return f'<td class="{cls}" data-col-idx="{idx}" rowspan="{rowspan}" style="{style}">{safe_content}</td>'

        # 0-3: Merged Columns (NO, DIM, SUB, IND)
        for idx, key in enumerate(merge_keys): 
            span = row_spans[i][key]
            if span != -1:
                # FIX: Pass the specific CSS class (e.g., 'col-no')
                html += make_td(row.get(key), idx, css_class=col_css_map.get(key, ""), rowspan=span, is_merged=(span > 1))

        # 4: ITEM
        html += make_td(row.get("ITEM"), 4, css_class="col-item")

        # 5-10: SCORES
        score_keys = ["SKOR Rata-Rata", "SKOR 1", "SKOR 2", "SKOR 3", "SKOR 4", "SKOR 5"]
        for idx, key in enumerate(score_keys, 5):
            val = row.get(key)
            display = val if val is not None else ""
            html += f'<td class="col-score" data-col-idx="{idx}" style="text-align:center;">{display}</td>'

        # 11: INTERVENSI
        html += make_td(row.get("INTERVENSI KEGIATAN"), 11, css_class="col-intervensi")

        # 12-16: PELAKSANA
        pelaksana_keys = ["PUSAT", "PROVINSI", "KABUPATEN", "DESA", "Lainnya"]
        pelaksana_css = ["col-pusat", "col-prov", "col-kab", "col-desa", "col-lain"]
        for j, suffix in enumerate(pelaksana_keys):
            idx = 12 + j
            key = f"PELAKSANA KEGIATAN {suffix}"
            html += make_td(row.get(key), idx, css_class=pelaksana_css[j])

        html += "</tr>"

    html += "</tbody>"
    return html
