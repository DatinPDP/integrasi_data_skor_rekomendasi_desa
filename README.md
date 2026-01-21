# Config
```
/root
/.config/headers.txt
/.config/intervensi_kegiatan.json
/.config/rekomendasi.json
/.config/table_structure.csv
```
# Requirements
Python 3.11.9

run this at start
```bash
Python311 -m venv .venv
source .venv/Scripts/activate
pip install -r .config/requirements.txt
```

# Run backend+middleware
run backend
```bash
python desa_db/server.py
```

or run both front and backend
```bash
python run_system.py
```
nodejs requirements
```
npm install ag-grid-react ag-grid-community xlsx
npm install -D tailwindcss postcss autoprefixer
```

run frontend nextjs
```
cd js_front_end
npm run dev
```

# Run mock frontend
```bash
streamlit run tests/test_serverSheets.py
```

To run the tests for the server, use the following command in your terminal:
```bash
pytest tests/test_server.py
```
