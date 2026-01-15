import polars as pl
import json
import os

# ==========================================
# CONFIGURATION
# ==========================================
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


# Get the directory where THIS file (middleware.py) is located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Point to ../.config/rekomendasi.json relative to this file
JSON_PATH = os.path.abspath(os.path.join(BASE_DIR, "../.config/rekomendasi.json"))

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
    
    # 1. Build the list of instructions (Lazy Evaluation)
    for col_name, logic_map in RECOMMENDATION_LOGIC.items():
        if col_name in df.columns:
            expr = (
                pl.col(col_name)
                # Cast to Int64 to ensure "5.0" (float) or "5" (str) matches the dictionary keys (1,2,3,4)
                .cast(pl.Int64, strict=False) # Ensure we are matching numbers
                # This explicitly handles the 'default' and 'return_dtype' logic
                .replace_strict(logic_map, default=None, return_dtype=pl.String)
                .alias(col_name)
            )
            exprs.append(expr)
    
    # 2. Execute all instructions at once
    if exprs:
        return df.with_columns(exprs)
    
    return df

