import sys
import os
import json
import csv
import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

# ==========================================
# PATH FIX FOR IMPORTS
# ==========================================
# Add the 'desa_db' directory to the Python path so we can import server and middleware
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
DESA_DB_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "../desa_db"))
sys.path.insert(0, DESA_DB_DIR)

# Now we can import from the desa_db folder
import server
import middleware

# ==========================================
# FIXTURES (Setup Mock Environment)
# ==========================================

@pytest.fixture(scope="session")
def test_year():
    return "2023"

@pytest.fixture(autouse=True)
def setup_environment(tmp_path, monkeypatch):
    """
    Creates a temporary directory structure and overrides all absolute paths 
    in the server and middleware modules to prevent touching real files.
    """
    # 1. Create temporary directories
    config_dir = tmp_path / ".config"
    db_dir = tmp_path / "dbs"
    staging_dir = tmp_path / "staging"
    
    config_dir.mkdir()
    db_dir.mkdir()
    staging_dir.mkdir()

    # 2. Patch absolute paths in BOTH modules
    monkeypatch.setattr(middleware, "CONFIG_DIR", str(config_dir))
    monkeypatch.setattr(middleware, "DB_FOLDER", str(db_dir))
    monkeypatch.setattr(middleware, "STAGING_FOLDER", str(staging_dir))
    monkeypatch.setattr(server, "CONFIG_DIR", str(config_dir))
    monkeypatch.setattr(server, "STAGING_FOLDER", str(staging_dir))
    monkeypatch.setattr(middleware, "INTERVENTION_FILE", str(config_dir / "intervensi_kegiatan.json"))
    monkeypatch.setattr(server, "HEADER_FILE", str(config_dir / "headers.txt"))

    # 3. Create mock headers.txt
    headers = [
        "Kode Wilayah Administrasi Desa", "Desa", "Kecamatan", 
        "Kabupaten/ Kota", "Provinsi", "TAHUN DATA", "Score A", "Score B"
    ]
    with open(config_dir / "headers.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(headers))

    # 4. Create mock table_structure.csv
    with open(config_dir / "table_structure.csv", "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["DIMENSI", "ITEM"])
        writer.writerow(["Dimensi 1", "Score A"])
        writer.writerow(["Dimensi 2", "Score B"])

    # 5. Create mock rekomendasi.json
    mock_logic = {
        "Score A": { "1": "Sangat Kurang A", "5": "Sangat Baik A" }
    }
    with open(config_dir / "rekomendasi.json", "w", encoding="utf-8") as f:
        json.dump(mock_logic, f)

    return tmp_path

@pytest.fixture
def client():
    """Provides a FastAPI test client."""
    return TestClient(server.app)

@pytest.fixture
def mock_excel(tmp_path):
    """
    Generates a valid temporary .xlsx file configured exactly 
    how the polars 'calamine' engine expects it in server.py (skipping first 3 rows).
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Skor"

    # Row 1-3: Garbage titles (server.py slices 3 rows)
    ws.append(["JUDUL LAPORAN"])
    ws.append(["SUB JUDUL"])
    ws.append(["--- EMPTY METADATA ROW ---"])

    # Row 4: Headers (matches mock headers.txt)
    ws.append([
        "Index", "Kode Wilayah Administrasi Desa", "Desa", "Kecamatan", 
        "Kabupaten/ Kota", "Provinsi", "TAHUN DATA", "Score A", "Score B"
    ])

    # Row 5+: Valid Data (ID must be 10 digits as per regex)
    ws.append([1, "1111111111", "Desa Mock", "Kec Mock", "Kab Mock", "Prov Mock", "2023", 1, 5])
    ws.append([2, "2222222222", "Desa Dua", "Kec Mock", "Kab Mock", "Prov Mock", "2023", 4, 3])

    excel_path = tmp_path / "test_upload.xlsx"
    wb.save(excel_path)
    return excel_path

# ==========================================
# TESTS
# ==========================================

def test_get_table_structure(client):
    """Tests the /config/table_structure endpoint."""
    response = client.get("/config/table_structure")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["ITEM"] == "Score A"

def test_full_etl_pipeline(client, test_year, mock_excel):
    """
    Tests the sequential ETL flow:
    1. Upload/Stage
    2. Commit
    3. Query Data
    4. Calculate Dashboard
    5. Soft Delete
    6. History Diffs
    """

    # --- STEP 1: UPLOAD / STAGE ---
    with open(mock_excel, "rb") as f:
        response = client.post(
            f"/stage/{test_year}",
            files={"file": ("test_upload.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        )
    
    assert response.status_code == 200
    stage_data = response.json()
    assert stage_data["status"] == "staged"
    assert stage_data["diff"]["added"] == 2 # 2 new rows
    
    staging_id = stage_data["staging_id"]
    filename = stage_data["filename"]

    # --- STEP 2: COMMIT ---
    commit_response = client.post(
        f"/commit/{test_year}",
        params={"staging_id": staging_id, "filename": filename}
    )
    assert commit_response.status_code == 200
    assert commit_response.json()["status"] == "success"

    # --- STEP 3: QUERY ---
    # Test standard query
    query_response = client.get(f"/query/{test_year}?limit=50")
    assert query_response.status_code == 200
    q_data = query_response.json()
    assert len(q_data) == 2
    assert q_data[0]["Kode Wilayah Administrasi Desa"] == "1111111111"

    # Test dynamic filtering (e.g., specific Desa)
    filter_response = client.get(f"/query/{test_year}?Desa=Dua")
    assert filter_response.status_code == 200
    assert len(filter_response.json()) == 1

    # --- STEP 4: DASHBOARD CALCULATION ---
    calc_response = client.post(f"/dashboard/calculate/{test_year}")
    assert calc_response.status_code == 200
    calc_data = calc_response.json()
    assert len(calc_data) == 2 # Structure has 2 rows
    # Check if calculation populated (e.g., SKOR 1 count for Score A)
    assert calc_data[0]["ITEM"] == "Score A"
    assert calc_data[0]["SKOR 1"] == "1" # 1 row had score 1

    # --- STEP 5: VERSIONS & HISTORY ---
    hist_response = client.get(f"/history/versions/{test_year}")
    assert hist_response.status_code == 200
    hist_data = hist_response.json()
    assert len(hist_data["versions"]) == 1
    
    # Get the latest timestamp for details check
    latest_version = hist_data["versions"][0]["ts"]

    # --- STEP 6: HISTORY DETAILS (DIFF) ---
    details_response = client.get(f"/history/details/{test_year}?version={latest_version}")
    assert details_response.status_code == 200
    diff_data = details_response.json()["changes"]
    assert any(c["type"] == "ADD" for c in diff_data)

    # --- STEP 7: DELETE ---
    delete_response = client.post(
        f"/delete/{test_year}",
        params={"ids": "1111111111", "summary": "Test Delete"}
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["status"] == "success"
    assert delete_response.json()["deleted_count"] == 1

    # Verify ID is removed from standard query
    final_query = client.get(f"/query/{test_year}")
    assert len(final_query.json()) == 1 # Only "2222222222" remains

def test_stage_upload_missing_header_file(client, test_year, mock_excel, tmp_path, monkeypatch):
    """Tests failure when headers.txt is missing."""
    # Point header to a non-existent path
    monkeypatch.setattr(server, "HEADER_FILE", str(tmp_path / "not_exist.txt"))

    with open(mock_excel, "rb") as f:
        response = client.post(f"/stage/{test_year}", files={"file": ("test.xlsx", f)})
    
    assert response.status_code == 500
    assert "Configuration file not found" in response.json()["error"]
