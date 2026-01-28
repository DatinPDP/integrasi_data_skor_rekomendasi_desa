## Project Structure – Configuration Files
All configuration files are stored in the `.config/` directory:

```
/root
/.config/auth_users.json
/.config/headers.txt
/.config/intervensi_kegiatan.json
/.config/rekomendasi.json
/.config/table_structure.csv
```

## System Requirements
- Python 3.11.9

## 1. Virtual Environment Setup (run once)
```bash
Python311 -m venv .venv
source .venv/Scripts/activate
pip install -r .config/requirements.txt
```

## Run backend+middleware
run backend
```bash
python desa_db/server.py
```

### or run both front and backend
```bash
python run_system.py
```
# Add user
```
python add_user.py <user> <password>
```
it will be saved in .config/

# nodejs requirements
```
npm install ag-grid-react ag-grid-community xlsx
npm install -D tailwindcss postcss autoprefixer
npm install spark-md5
```
# run frontend nextjs
```
cd js_front_end
npm run dev
```

## Run mock frontend
```bash
streamlit run tests/test_serverSheets.py
```

To run the tests for the server, use the following command in your terminal:
```bash
pytest tests/test_server.py
```
