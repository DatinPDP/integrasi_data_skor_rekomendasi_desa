import os
import sys
import pytest
import polars as pl
from fastapi.testclient import TestClient

# ==========================================
# PATH CONFIGURATION
# ==========================================
# Add the project root to sys.path so we can import from 'desa_db'
# We assume 'tests' is one level below root, and 'desa_db' is also one level below root.
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, ".."))
# 1. Add Project Root (Allows: from desa_db.server import ...)
sys.path.insert(0, project_root)

# 2. Add 'desa_db' folder (Allows server.py to do: from middleware import ...)
sys.path.insert(0, os.path.join(project_root, "desa_db"))

# ==========================================
# IMPORTS
# ==========================================
# Import server and middleware modules directly so we can patch them
import desa_db.server as server_module
import desa_db.middleware as middleware_module
from desa_db.server import app, DB_FOLDER, ID_COL

client = TestClient(app)

# ==========================================
# TEST SETUP
# ==========================================
TEST_YEAR = "test_2025"
TEST_DB_PATH = os.path.join(DB_FOLDER, f"data_{TEST_YEAR}.duckdb")
# will create this file locally during test, NOT in .config
TEST_HEADER_FILE_PATH = os.path.join(current_dir, "temp_test_headers.txt") 
# Pick one column from your logic to test
TEST_LOGIC_COL = "Ketersediaan PAUD/ TK/ Sederajat di Desa"

# Mock Rules for Middleware
TEST_RULES = {
    TEST_LOGIC_COL: {
        1: "Perlu menyediakan PAUD", # Value 1 translates to this
        5: None
    }
}

@pytest.fixture(autouse=True)
def setup_teardown():
    """
    Safely sets up test environment:
    1. Creates a TEMP header file (does not touch real config).
    2. Patches server.HEADER_FILE to point to the temp file.
    3. Patches middleware logic.
    """
    # 1. Create a temporary headers.txt just for this test
    with open(TEST_HEADER_FILE_PATH, "w", encoding="utf-8") as f:
        f.write(f"{ID_COL}\nNama Desa\n{TEST_LOGIC_COL}")

    # 2. SAVE ORIGINAL STATES (So we don't break the app)
    original_header_path = server_module.HEADER_FILE
    original_logic = middleware_module.RECOMMENDATION_LOGIC

    # 3. APPLY PATCHES
    # Tell server.py to read our temp file, not the real one
    server_module.HEADER_FILE = TEST_HEADER_FILE_PATH
    # Inject test logic
    middleware_module.RECOMMENDATION_LOGIC = TEST_RULES

    # 4. Clean DB
    if os.path.exists(TEST_DB_PATH):
        try: os.remove(TEST_DB_PATH)
        except: pass

    yield # Run Test

    # 5. RESTORE STATE (Safety)
    server_module.HEADER_FILE = original_header_path
    middleware_module.RECOMMENDATION_LOGIC = original_logic

    # 6. Cleanup Temp Files
    if os.path.exists(TEST_DB_PATH):
        try: os.remove(TEST_DB_PATH)
        except: pass
    if os.path.exists(TEST_HEADER_FILE_PATH):
        try: os.remove(TEST_HEADER_FILE_PATH)
        except: pass

def create_dummy_xlsb(filename):
    """Helper to create a valid dummy Excel file with the correct sheet name"""
    # The server drops Column A (df[:, 1:]), so our data must start from Column B.
    df = pl.DataFrame({
        # Column 0: Index (Dropped by server logic)
        "Index": ["", "", "", "", "", "", "", ""], 
        
        # Column 1: Metadata + ID_COL (The ID value "1234567890")
        "A": ["metadata", "metadata", "metadata", "metadata", "metadata", "metadata", ID_COL, "1234567890"],
        
        # Column 2: Metadata + Generic Data
        "B": ["", "", "", "", "", "", "Nama Desa", "Desa Test"],
        
        # Column 3: Metadata + THE COLUMN WE WANT TO TRANSLATE
        # We put "1" here. Middleware should convert this to text.
        "C": ["", "", "", "", "", "", TEST_LOGIC_COL, "1"] 
    })
 
    # Explicitly name the worksheet "Skor"
    df.write_excel(filename, worksheet="Skor")
    return filename

def test_upload_and_download_flow():
    """
    Integration Test:
    1. Upload a file to initialize the DB.
    2. Request a download of that data.
    3. Verify the downloaded file is a valid Excel file containing the data.
    """
    
    # 1. Create and Upload Dummy File in current test dir
    dummy_file = os.path.join(current_dir, "test_upload.xlsx")
    create_dummy_xlsb(dummy_file)
    downloaded_file = os.path.join(current_dir, "downloaded_test.xlsx")
 
    try:
        with open(dummy_file, "rb") as f:
            response = client.post(
                f"/upload/{TEST_YEAR}", 
                files={"file": ("test_upload.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            )
        assert response.status_code == 200

        # 2. Request Download
        download_response = client.get(f"/download/{TEST_YEAR}")
        
        # 3. Assertions
        assert download_response.status_code == 200
        
        # 4. Verify Content
        downloaded_file = "downloaded_test.xlsx"
        with open(downloaded_file, "wb") as f:
            f.write(download_response.content)
        
        df_downloaded = pl.read_excel(downloaded_file)
        
        # Polars often infers numeric strings (12345) as Integers.
        # cast to String to ensure our comparison works.
        df_downloaded = df_downloaded.with_columns(pl.col(ID_COL).cast(pl.String))
        
        # Check if our ID exists in the downloaded file
        assert ID_COL in df_downloaded.columns
        assert df_downloaded.filter(pl.col(ID_COL) == "1234567890").height == 1

        # 5. CHECK MIDDLEWARE LOGIC
        # The column should no longer contain "1", but the text recommendation
        res_trans = client.get(f"/query/{TEST_YEAR}?translate=true")
        assert res_trans.status_code == 200
        data_trans = res_trans.json()
        trans_value = data_trans[TEST_LOGIC_COL][0]

        print(f"Translated Value: {trans_value}")
        assert "Perlu menyediakan PAUD" in trans_value

    finally:
        # Cleanup local test artifacts
        if os.path.exists(dummy_file):
            try: os.remove(dummy_file)
            except: pass
        if os.path.exists(downloaded_file):
            try: os.remove(downloaded_file)
            except: pass
