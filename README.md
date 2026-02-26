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
- (Recommended) any cpu supported with AVX2 (earliest Intel 4th gen, AMD Ryzen)

## (Recommended) Run docker

create .env file
copy and paste this below
```
APP_SECRET_KEY=
```

generate APP_SECRET_KEY with command below:
```
openssl rand -hex 32
```
and put into .env

compile tailwind css v4 from input.css to output.css
```
npm init -y
npm install tailwindcss @tailwindcss/cli

npx @tailwindcss/cli -i ./front_end/static/css/input.css -o ./front_end/static/css/output.css --watch
```

you need to install docker & docker-compose if you haven't
on windows wsl is recommended
```
docker compose up -d --build
```
the behaviour at start will always try to make excel files ready to download from db

# Add user
```
python add_user.py <username> <password> <role>
python add_user.py admin MySecretPass123 admin
```
it will be saved in .config/

# Below are not recommended =====================================================

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

### (deprecated) Run mock frontend
```bash
streamlit run tests/serverSheets_test.py
```
