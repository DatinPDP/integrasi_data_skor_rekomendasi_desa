# Configuration Files
All configuration files are stored in the `.config/` directory:

```
/root
/.config/auth_users.json
/.config/headers.json
/.config/intervensi_kegiatan.json
/.config/rekomendasi.json
/.config/table_structure.csv
```

# System Requirements
- Python 3.11.9
- (Recommended) any cpu supported with AVX2 (earliest Intel 4th gen, AMD Ryzen)

## (Recommended) Run docker

### Add user
```
python add_user.py <username> <password> <role>
python add_user.py admin MySecretPass123 admin
```
it will be saved in .config/

### .env
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

### compile tailwindcss (if output.css doesn't exist)
compile tailwind css v3 from input.css to output.css
```
cd front_end/
npm install -D tailwindcss@3 postcss autoprefixer
npx tailwindcss init
```

on tailwind.config.js paste this below
```
/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  // Use **/*.html to scan all folders in the project for HTML files
  content: ["./**/*.html", "./static/**/*.js"], 
  theme: {
    extend: {},
  },
  plugins: [],
}

```

then compile it

```
npx tailwindcss -i ./static/css/input.css -o ./static/css/output.css --watch
```
### Run docker
you need to install docker & docker-compose if you haven't
on windows wsl is recommended
```
docker compose up -d --build
```
the behaviour at start will always try to make excel files ready to download from db

## Run test
```
pytest tests/server_test.py
```

## Below are not recommended =====================================================

### Virtual Environment Setup (run once)
```bash
Python311 -m venv .venv
source .venv/Scripts/activate
pip install -r .config/requirements.txt
```

### Run backend+middleware
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
