# Ditjen PDP Development Reference

## 1. Purpose

This document is the technical reference for development and operations of `integrasi_data_skor_rekomendasi_desa`. It covers architecture, security, data update flow, deployment, and release quality gates.

## 1.1 Language Policy

- Use English for coding tasks, technical implementation notes, and development instructions.
- Keep project-specific terminology that is already standard in this repository.
- Use Indonesian for executive dashboard audience-facing content text.
- Keep code, identifiers, and technical documentation structure in English.

## 2. System Architecture

- Backend API: `desa_db/server.py`
- Data/report middleware: `desa_db/middleware.py`
- Frontend router: `front_end/router.py`
- Reverse proxy: `nginx.conf`
- Container orchestration: `docker-compose.yml`
- Authentication module: `desa_db/auth.py`, `add_user.py`

Public entry point:

- `http://<host>:8080` (via Nginx)

## 3. Branching and Release Policy

- `dev`: active development branch.
- `main`: production branch.

Policy:

1. Implement all feature/fix work in `dev`.
2. Complete local validation in `dev`.

## 4. Core Configuration Files

Main configuration lives in `.config/`:

- `auth_users.json`
- `headers.json`
- `rekomendasi.json`
- `table_structure.csv`
- `table_structure_IKU.csv`
- `iku_mapping.json`
- `intervensi_kegiatan_mapping.json`

Any change in these files directly affects query behavior, scoring, recommendations, and dashboard outputs.

## 5. Minimum Security Requirements

- `.env` with `APP_SECRET_KEY` is mandatory.
- Authentication endpoints:
  - `POST /api/login`
  - `POST /api/logout`
- Session token is JWT stored as HttpOnly cookie.
- Upload/process endpoints are admin-only.

## 6. Official Data Update SOP

Do not update tables manually. Use the official API flow:

1. `POST /upload/init/{year}`
2. `POST /upload/chunk/{year}`
3. `POST /upload/finalize/{year}`
4. `POST /preview_excel/{year}`
5. `POST /analyze_header/{year}`
6. `POST /process_excel/{year}`
7. Commit data through admin/backend flow and verify outputs.

Year-based active database convention:

- `desa_db/dbs/data_<year>.duckdb`

## 7. Local Runbook (Technical)

Prerequisites:

- Docker daemon is running.
- `.env` exists.

Run:

```bash
docker compose up -d --build
docker compose ps
```

Enforcement:

- Use `docker compose up -d --build` exclusively for local run/rebuild.
- Rebuild on every change to keep backend/frontend/nginx artifacts in sync.

## 8. Minimum Validation Endpoints

- Auth:
  - `POST /api/login`
  - `POST /api/logout`
- Data pipeline:
  - `/upload/init/{year}`
  - `/upload/chunk/{year}`
  - `/upload/finalize/{year}`
  - `/preview_excel/{year}`
  - `/analyze_header/{year}`
  - `/process_excel/{year}`
- Data consumption:
  - `/query/{year}`
  - year-specific dashboard endpoints
  - year-specific history/versions endpoints

## 9. Pre-Release QA Checklist

1. `backend`, `frontend`, `nginx`, and `backup` services are `Up`.
2. Admin login works.
3. Target-year query endpoint does not return 500.
4. Recommendation and IKU dashboards load correctly.
5. Excel export works.
6. Backend logs do not contain `database does not exist`.
7. No sensitive files are committed.

## 10. Common Troubleshooting

- `No Rows To Show`: active-year DB file missing or wrong year selected in UI.
- `Cannot open database ... data_<year>.duckdb`: that year database file is not available.
- Login issues: validate `.config/auth_users.json` and `APP_SECRET_KEY`.
- Dashboard rendering issues: inspect backend/frontend/nginx status and compose logs.

## 11. Current Local Data Validation Notes

- `data_2025.duckdb` is available in `desa_db/dbs/`.
- `master_data` table is present and contains rows.
- Public 2025 dashboard endpoint responds normally.
- Other years require their corresponding `data_<year>.duckdb` files.
