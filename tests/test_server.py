import os
import sys
import pytest
import polars as pl
from fastapi.testclient import TestClient
import json

# ==========================================
# 1. PATH CONFIGURATION
# ==========================================
# We need to add the project root to sys.path so we can import 'desa_db'
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, ".."))

# Add root folder (for 'desa_db' package resolution)
sys.path.insert(0, project_root)
# Add 'desa_db' folder (for internal imports inside server.py)
sys.path.insert(0, os.path.join(project_root, "desa_db"))

# ==========================================
# 2. IMPORTS & MOCKING TARGETS
# ==========================================
# We import the modules *directly* so we can overwrite their variables
import desa_db.server as server_module
import desa_db.middleware as middleware_module
from desa_db.server import app, DB_FOLDER, ID_COL, STAGING_FOLDER

client = TestClient(app)

# ==========================================
# 3. TEST CONSTANTS
# ==========================================
TEST_YEAR = "test_2025"
TEST_DB_PATH = os.path.join(DB_FOLDER, f"data_{TEST_YEAR}.duckdb")

# We will create this file locally inside /tests/, avoiding the real .config folder
TEST_HEADER_FILE_PATH = os.path.join(current_dir, "temp_test_headers.txt") 

# This is the column we will test translation on
TEST_LOGIC_COL = "Ketersediaan PAUD/ TK/ Sederajat di Desa"

# Mock Rules for Middleware (Since the real JSON might not exist in test env)
TEST_RULES = {
    TEST_LOGIC_COL: {
        1: "Perlu menyediakan PAUD", # Value 1 translates to this
        5: None
    }
}

# ==========================================
# 4. FIXTURE (SETUP & TEARDOWN)
# ==========================================
@pytest.fixture(autouse=True)
def setup_teardown():
    """
    Safely sets up test environment:
    1. Creates a TEMP header file.
    2. PATCHES server.py to read our temp file instead of real config.
    3. PATCHES middleware.py to use our TEST_RULES instead of reading JSON.
    4. Cleans up afterwards.
    """
    # --- SETUP ---
    # HEADERS: Must include Location columns for the Hierarchy Cache to work
    headers = [
        ID_COL,
        "Nama Desa",
        "Provinsi",
        "Kabupaten/ Kota",
        "Kecamatan",
        TEST_LOGIC_COL
    ]
    
    # Create a temporary headers.txt just for this test
    with open(TEST_HEADER_FILE_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(headers))

    # 2. SAVE ORIGINAL STATES (So we don't break the actual app config)
    original_header_path = server_module.HEADER_FILE
    original_logic = middleware_module.RECOMMENDATION_LOGIC

    # APPLY PATCHES (The Magic)
    # Tell server.py: "Don't look at .config, look at this temp file"
    server_module.HEADER_FILE = TEST_HEADER_FILE_PATH
    
    # Tell middleware.py: "Don't load JSON, use this dict"
    middleware_module.RECOMMENDATION_LOGIC = TEST_RULES

    # Clean previous DB artifacts
    if os.path.exists(TEST_DB_PATH):
        try: os.remove(TEST_DB_PATH)
        except: pass
    # Ensure staging folder exists
    os.makedirs(STAGING_FOLDER, exist_ok=True)

    yield

    # --- TEARDOWN ---
    
    # RESTORE ORIGINAL STATE
    server_module.HEADER_FILE = original_header_path
    middleware_module.RECOMMENDATION_LOGIC = original_logic

    # Define files to clean
    # Note: We must locate the cache file exactly where server.py put it (.config folder)
    real_config_dir = os.path.abspath(os.path.join(current_dir, "../.config"))
    cache_file = os.path.join(real_config_dir, f"unique_cache_{TEST_YEAR}.json")

    files_to_clean = [
        TEST_DB_PATH, 
        TEST_HEADER_FILE_PATH, 
        os.path.join(current_dir, "test_upload.xlsx"), 
        os.path.join(current_dir, "downloaded_test.xlsx"),
        cache_file
    ]

    # Cleanup Temp Files
    for f in files_to_clean:
        if os.path.exists(f):
            try: os.remove(f)
            except: pass


# ==========================================
# 5. HELPER FUNCTION
# ==========================================
def create_dummy_xlsb(filename):
    """
    Creates dummy data WITH Location columns so cache generation succeeds.
    Note: Writes as .xlsx (XML format) via xlsxwriter default.
    """
    df = pl.DataFrame({
        # Column 0: Index (Dropped)
        "Index": [""] * 8, 
        
        # Column 1: ID
        "A": ["metadata"]*6 + [ID_COL, "1234567890"],
        
        # Column 2: Nama Desa
        "B": [""]*6 + ["Nama Desa", "Desa Test"],
        
        # Column 3: Provinsi
        "C": [""]*6 + ["Provinsi", "Jawa Barat"],
        
        # Column 4: Kab
        "D": [""]*6 + ["Kabupaten/ Kota", "Bandung"],
        
        # Column 5: Kec
        "E": [""]*6 + ["Kecamatan", "Coblong"],
        
        # Column 6: Logic
        "F": [""]*6 + [TEST_LOGIC_COL, "1"] 
    })
 
    # Explicitly name the worksheet "Skor"
    df.write_excel(filename, worksheet="Skor")
    return filename

# ==========================================
# 6. THE TEST
# ==========================================
def test_staging_and_commit_flow():
    """
    Integration Test: Stage -> Commit -> Query
    """
    
    # Paths for temp files
    dummy_file = os.path.join(current_dir, "test_upload.xlsx")
    downloaded_file = os.path.join(current_dir, "downloaded_test.xlsx")
    
    create_dummy_xlsb(dummy_file)

    try:
        # --- STEP 1: STAGE (Analyze) ---
        with open(dummy_file, "rb") as f:
            # We explicitly name it .xlsx so the server preserves the extension
            stage_response = client.post(
                f"/stage/{TEST_YEAR}", 
                files={"file": ("test_upload.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            )
        
        # Debugging output if it fails
        if stage_response.status_code != 200:
            print(f"\nStage Error: {stage_response.text}")

        assert stage_response.status_code == 200
        stage_data = stage_response.json()
        
        # Verify Staging Response Structure
        assert "staging_id" in stage_data
        assert "diff" in stage_data
        assert stage_data["diff"]["added"] == 1
        
        staging_id = stage_data["staging_id"]

        # --- STEP 2: COMMIT (Write to DB) ---
        commit_response = client.post(
            f"/commit/{TEST_YEAR}", 
            params={"staging_id": staging_id, "filename": "test_upload.xlsx"}
        )
        assert commit_response.status_code == 200

        # --- STEP 3: HIERARCHY CHECK ---
        res_hierarchy = client.get(f"/hierarchy/{TEST_YEAR}")
        assert res_hierarchy.status_code == 200
        tree = res_hierarchy.json()
        assert "Jawa Barat" in tree

        # --- STEP 4: DOWNLOAD ---
        download_response = client.get(f"/download/{TEST_YEAR}")
        assert download_response.status_code == 200
        with open(downloaded_file, "wb") as f:
            f.write(download_response.content)

        # --- STEP 5: QUERY & TRANSLATION ---
        res_trans = client.get(f"/query/{TEST_YEAR}?translate=true")
        assert res_trans.status_code == 200
        data_trans = res_trans.json()
        
        # Handle list-of-dicts format (New Server Standard)
        assert isinstance(data_trans, list)
        assert len(data_trans) > 0
        first_row = data_trans[0]
        assert "Perlu menyediakan PAUD" in first_row[TEST_LOGIC_COL]

    finally:
        if os.path.exists(dummy_file): os.remove(dummy_file)
        if os.path.exists(downloaded_file): os.remove(downloaded_file)
