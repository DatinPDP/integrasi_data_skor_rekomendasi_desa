# One-Page Operations Runbook
## Ditjen PDP Information System

## Purpose
Quick guide for non-technical operators to:
- start the system,
- verify system health,
- recover when data is not displayed.

## Application Access
- Local URL: `http://127.0.0.1:8080`
- Sign in using a registered admin/operator account.

## Daily Check (5-10 minutes)
1. Open the app and sign in.
2. Confirm dashboard loads normally.
3. Select the correct data year (for example, 2025).
4. Check the data grid:
   - if data appears: operations are normal.
   - if empty: follow "If Data Does Not Appear".
5. Confirm upload/download and history menus work.

## Restart Procedure (When Needed)
Ask the technical team to run:
```bash
docker compose up -d --build
docker compose ps
```

Use `docker compose up -d --build` for every restart/rebuild after changes.

Healthy status means all services are `Up`:
- `backend_id_srd_iku`
- `frontend_id_srd_iku`
- `nginx_id_srd_iku`
- `backup_id_srd_iku`

## If Data Does Not Appear
Symptoms:
- `No Rows To Show`
- empty dashboard
- village count is 0

Steps:
1. Confirm selected year matches available data.
2. Logout and login again.
3. Hard refresh browser (`Cmd + Shift + R` on Mac).
4. If still empty, escalate to technical team with:
   - time of issue,
   - selected year,
   - screenshot.

Technical note:
- The system reads year-based files `data_<year>.duckdb`.
- If that year file does not exist, data will not appear.

## Data Update Procedure (Operator Version)
1. Sign in as admin.
2. Use the data upload menu.
3. Wait until upload and processing complete.
4. Run commit/save through the admin UI flow.
5. Verify:
   - grid contains data,
   - recommendation dashboard loads,
   - IKU dashboard loads.

## Do Not
- Do not manually edit configuration files.
- Do not delete database files.
- Do not share admin credentials.

## When to Escalate
Escalate immediately if:
- repeated login failures,
- recurring 500 errors,
- data remains empty after relogin and refresh,
- repeated Excel export failures.

## Minimum Escalation Info
- accessed URL
- username (never share password)
- selected year
- screenshot of error/screen
- timestamp of issue
