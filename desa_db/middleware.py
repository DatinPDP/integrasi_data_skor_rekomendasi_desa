import os
import json
import re
import duckdb
import html as h
import polars as pl
from fastapi import Response
from fastapi.responses import JSONResponse
 
# ==========================================
# CONFIGURATION
# ==========================================
# /root
#   /root
#   /.config/headers.txt
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
 
# Header File: inside .config/headers.txt (sibling of desa_db)
HEADER_FILE = os.path.join(CONFIG_DIR, "headers.txt")
 
# Data Structure Constants
# ID_COL acts as the Primary Key for deduplication and version control.
ID_COL = "Kode Wilayah Administrasi Desa" 
 
 
# Point to ../.config/rekomendasi.json relative to this file
os.makedirs(DB_FOLDER, exist_ok=True)
 
# ==========================================
# LOGIC LOADER (Existing)
# ==========================================
def load_logic():
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
    Apply all 120+ rules in a SINGLE pass (Batch Execution).
    This allows Polars to optimize the plan and execute in parallel.
    Uses replace_strict to avoid DeprecationWarnings in Polars 1.0+.
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
    Directly converts Polars DataFrame to JSON string, bypassing 
    Python's slow list-of-dicts conversion.
    In newer Polars versions, write_json() defaults to row-oriented (list of dicts).
    """
    # Serialize directly to JSON string using Rust engine
    json_str = df.write_json()
 
    # Return direct Response (skips FastAPI's jsonable_encoder overhead)
    return Response(content=json_str, media_type="application/json")
 
# ==========================================
# DATABASE HELPERS
# ==========================================
 
# INTERNAL FILE PROCESSOR, staging uploads basically
def helpers_internal_process_staging_file(year: str, file_path: str, filename: str, staging_id: str):
    """
    Core Logic extracted from endpoint_post_stage_upload.
    Parses the file (XLSX/XLSB) and compares with DB.
 
    Ingests an Excel (.xlsb) file, cleans it, and performs a "Change Data Capture" (CDC) update.
 
    Workflow:
    1. Read Excel via Polars.
    2. clean structural garbage (headers/empty cols).
    3. Compare new data against existing DB data.
    4. Archive changed rows to 'history'.
    5. Upsert (Update/Insert) new rows to 'master_data'.
 
    """
    try:
        # --- Load Schema Definition ---
        # Ideally, load this from a config file.
        if not os.path.exists(HEADER_FILE):
             raise Exception(f"Configuration file not found: {HEADER_FILE}")
 
        with open(HEADER_FILE, "r", encoding="utf-8") as f:
            stage_upload_header = [line.strip() for line in f if line.strip()]
 
        # --- ETL: Extraction & Cleaning (Polars) ---
        print(f"Processing {filename} for year {year}...")
 
        # Read .xlsb/.xlsx using 'calamine'
        df = pl.read_excel(
            file_path,
            sheet_name="Skor",
            engine="calamine",
        )
 
        # Structure Cleaning:
        # Slice: Cap width to prevent reading infinite empty Excel columns
        max_col = min(df.width, 262) 
        # Also skip the very first index column (0)
        df = df[:, 1:max_col]

        # Validation check
        # expect the first row (now at index 1) to be the headers
        current_headers = df.row(1)
        
        # Define the exact expected order for the first 5 columns
        expected_order = [
            'Provinsi', 
            'Kabupaten/ Kota', 
            'Kecamatan', 
            'Kode Wilayah Administrasi Desa', 
            'Desa'
        ]

        # Check the first 5 columns
        found_order = [str(h).strip() for h in current_headers[:5]]
        
        if found_order != expected_order:
            for i, (exp, fnd) in enumerate(zip(expected_order, found_order)):
                if exp != fnd:
                    # Returns concise error: "Header Mismatch (Col 1): Expected 'Provinsi' vs 'ACEH'"
                    raise Exception(f"Header Mismatch (Col {i+1}): Expected '{exp}' vs '{fnd}'")
            
            # Fallback for length mismatches
            raise Exception(f"Header Mismatch: Expected {len(expected_order)} columns, found {len(found_order)}")

        # Where the data actually is
        df = df.slice(3, None)
        
        # Validation check column after 'Desa' (Index 5)
        # ensure this column is NOT a number
        if df.width > 5:
            col_after_desa = df[:, 5]

            # 1. Strict Dtype Check (Catch if Polars explicitly sees numbers)
            if col_after_desa.dtype in [pl.Int8, pl.Int16, pl.Int32, pl.Int64, pl.Float32, pl.Float64]:
                 raise Exception("Format Error: The column after 'Desa' is numeric (Dtype). It should be text.")
            
            # 2. Content Check (Catch "2025" hidden inside a String column)
            # - "MAJU" becomes Null (Safe)
            # - "2025" becomes 2025.0 (Detected)
            numeric_hits = col_after_desa.cast(pl.Float64, strict=False).is_not_null().sum()
            
            if numeric_hits > 0:
                 raise Exception(f"Error: column after 'Desa' contains numbers (found {numeric_hits} numeric values). It should be text status.")
 
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
 
        # OPTIMIZATION
        # Identify Text Columns (same as middleware)
        TEXT_COLUMNS = {
            "Provinsi", "Kabupaten/ Kota", "Kecamatan", 
            "Kode Wilayah Administrasi Desa", "Desa", "Status ID"
        }
 
        # Identify Score Columns
        score_cols = [c for c in df.columns if c not in TEXT_COLUMNS]
 
        # Cast Score Columns to Int8 (TINYINT)
        # strict=False converts non-numeric garbage to Null
        if score_cols:
            df = df.with_columns(
                [pl.col(c).cast(pl.Int8, strict=False) for c in score_cols]
            )
 
        # Cast Identity Columns to String (Ensure IDs are not read as numbers)
        ident_cols = [c for c in df.columns if c in TEXT_COLUMNS]
        if ident_cols:
             df = df.with_columns(
                [pl.col(c).cast(pl.String) for c in ident_cols]
            )
        # OPTIMIZATION END
 
        # Save Staged Data (Parquet will now store these as Integers)
        final_parquet_path = os.path.join(STAGING_FOLDER, f"{staging_id}.parquet")
        df.write_parquet(final_parquet_path)
 
        # --- Database Merge Logic (DuckDB) ---
        con, db_path = helpers_get_db_connection(year)
        helpers_init_db(con, df.columns)
 
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
    clean_year = os.path.basename(year)

    if not re.match(r'^20\d{2}$', clean_year):
        raise ValueError(f"Year must start with 20XX, got: '{clean_year}'")

    db_path = os.path.join(DB_FOLDER, f"data_{clean_year}.duckdb")
    con = duckdb.connect(db_path)
    return con, db_path
 
def helpers_get_cache_path(year: str):
    """Returns the absolute path for the cache file for a specific year."""
    get_cache_path_clean_year = os.path.basename(year)
    return os.path.join(CONFIG_DIR, f"unique_cache_{get_cache_path_clean_year}.json")
 
def helpers_init_db(con: duckdb.DuckDBPyConnection, headers: list[str]):
    """
    SCD Type 2 Schema:
 
    Architecture:
    - valid_from: Timestamp when this row became active.
    - valid_to: Timestamp when this row was replaced/deleted (NULL = Currently Active).
    - commit_id: Groups changes by upload transaction.
    - Metadata/Identity columns -> VARCHAR
    - Score columns -> TINYINT (1 byte integer)
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
 
def helpers_build_dynamic_query(con, base_query, request_params):
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
 
def helpers_get_or_create_intervensi_kegiatan(items: list[str]):
    """
    Loads intervensi_kegiatan. If missing, creates a default file 
    using the ITEM names as keys.
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
    Core logic to calculate dashboard statistics(based on table_structure.csv) from a Polars DataFrame.
    Shared between Dashboard UI and Excel Export.
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
    Generates the full HTML Table (Thead + Tbody) server-side.
    with hooks for JS interaction.
    Replicates the 'Row Span' logic previously done in JavaScript.
    - Adds 'data-col-idx' to ALL cells (required for Column Freeze).
    - Adds 'resizer' div to Headers (required for Column Resize).
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
    # We pre-calculate spans to know when to output <td rowspan="X"> or skip
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
            # We add vertical-align: top to everything.
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
