import os
import sys
import pytest
import polars as pl
from fastapi.testclient import TestClient

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
from desa_db.server import app, DB_FOLDER, ID_COL

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
    
    # 1. Create a temporary headers.txt just for this test
    with open(TEST_HEADER_FILE_PATH, "w", encoding="utf-8") as f:
        f.write(f"{ID_COL}\nNama Desa\n{TEST_LOGIC_COL}")

    # 2. SAVE ORIGINAL STATES (So we don't break the actual app config)
    original_header_path = server_module.HEADER_FILE
    original_logic = middleware_module.RECOMMENDATION_LOGIC

    # 3. APPLY PATCHES (The Magic)
    # Tell server.py: "Don't look at .config, look at this temp file"
    server_module.HEADER_FILE = TEST_HEADER_FILE_PATH
    
    # Tell middleware.py: "Don't load JSON, use this dict"
    middleware_module.RECOMMENDATION_LOGIC = TEST_RULES

    # 4. Clean previous DB artifacts
    if os.path.exists(TEST_DB_PATH):
        try: os.remove(TEST_DB_PATH)
        except: pass

    yield # === RUN THE TEST ===

    # --- TEARDOWN ---
    
    # 5. RESTORE ORIGINAL STATE
    server_module.HEADER_FILE = original_header_path
    middleware_module.RECOMMENDATION_LOGIC = original_logic

    # 6. Cleanup Temp Files
    if os.path.exists(TEST_DB_PATH):
        try: os.remove(TEST_DB_PATH)
        except: pass
    if os.path.exists(TEST_HEADER_FILE_PATH):
        try: os.remove(TEST_HEADER_FILE_PATH)
        except: pass


# ==========================================
# 5. HELPER FUNCTION
# ==========================================
def create_dummy_xlsb(filename):
    """Creates a valid dummy Excel file matching server expectations."""
    df = pl.DataFrame({
        # Column 0: Index (Dropped by server logic)
        "Index": ["", "", "", "", "", "", "", ""], 
        
        # Column 1: Metadata + ID_COL (The ID value "1234567890")
        "A": ["metadata", "metadata", "metadata", "metadata", "metadata", "metadata", ID_COL, "1234567890"],
        
        # Column 2: Metadata + Generic Data
        "B": ["", "", "", "", "", "", "Nama Desa", "Desa Test"],
        
        # Column 3: Metadata + THE COLUMN WE WANT TO TRANSLATE
        # We put "1". Middleware should convert this to "Perlu menyediakan PAUD"
        "C": ["", "", "", "", "", "", TEST_LOGIC_COL, "1"] 
    })
    
    # Explicitly name the worksheet "Skor"
    df.write_excel(filename, worksheet="Skor")
    return filename

# ==========================================
# 6. THE TEST
# ==========================================
def test_upload_and_download_flow():
    """
    Integration Test:
    1. Upload a file to initialize the DB.
    2. Request a download of that data.
    3. Verify data integrity.
    4. Verify Middleware Translation logic.
    """
    
    # Paths for temp files
    dummy_file = os.path.join(current_dir, "test_upload.xlsx")
    downloaded_file = os.path.join(current_dir, "downloaded_test.xlsx")
    
    create_dummy_xlsb(dummy_file)

    try:
        # --- STEP 1: UPLOAD ---
        with open(dummy_file, "rb") as f:
            response = client.post(
                f"/upload/{TEST_YEAR}", 
                files={"file": ("test_upload.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            )
        
        if response.status_code != 200:
            print("\nServer Error:", response.json())
        assert response.status_code == 200
        assert response.json()["status"] == "success"

        # --- STEP 2: DOWNLOAD ---
        download_response = client.get(f"/download/{TEST_YEAR}")
        assert download_response.status_code == 200
        
        with open(downloaded_file, "wb") as f:
            f.write(download_response.content)
        
        # Verify ID exists in downloaded file
        df_downloaded = pl.read_excel(downloaded_file)
        df_downloaded = df_downloaded.with_columns(pl.col(ID_COL).cast(pl.String))
        assert df_downloaded.filter(pl.col(ID_COL) == "1234567890").height == 1

        # --- STEP 3: MIDDLEWARE CHECK ---
        # Request with ?translate=true
        res_trans = client.get(f"/query/{TEST_YEAR}?translate=true")
        assert res_trans.status_code == 200
        
        data_trans = res_trans.json()
        
        # Check if the column exists and has been translated
        if TEST_LOGIC_COL in data_trans:
            trans_value = data_trans[TEST_LOGIC_COL][0]
            print(f"Translated Value: {trans_value}")
            
            # This confirms the mocked middleware logic is working
            assert "Perlu menyediakan PAUD" in trans_value
        else:
            pytest.fail(f"Column '{TEST_LOGIC_COL}' not found in response JSON.")

    finally:
        # Cleanup
        if os.path.exists(dummy_file):
            try: os.remove(dummy_file)
            except: pass
        if os.path.exists(downloaded_file):
            try: os.remove(downloaded_file)
            except: pass
