## Configuration Files
All configuration files are stored in the `.config/` directory:

```
/root
/.config/auth_users.json
/.config/headers.json
/.config/intervensi_kegiatan.json
/.config/rekomendasi.json
/.config/table_structure.csv
```

## System Requirements
- Python 3.11.9

## Run docker
you need to install docker & docker-compose if you haven't
on windows wsl is recommended
```
docker compose up -d --build
```

## Virtual Environment Setup (run once)
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
python add_user.py <username> <password> <role>
python add_user.py admin MySecretPass123 admin
```
it will be saved in .config/

### (deprecated) nodejs requirements
```
npm install ag-grid-react ag-grid-community xlsx
npm install -D tailwindcss postcss autoprefixer
npm install spark-md5
```
### (deprecated) run frontend nextjs
```
cd js_front_end
npm run dev
```

### (deprecated) Run mock frontend
```bash
streamlit run tests/test_serverSheets.py
```
