---
name: pdp-system-guide
description: Use this skill when developing, operating, or updating data in integrasi_data_skor_rekomendasi_desa to stay aligned with the official architecture, upload-process-commit SOP, and dev-to-main release flow.
---

# PDP System Guide

## When to use
Use this skill whenever work touches one of these areas:

- backend, frontend, or infrastructure changes in this project,
- yearly village data updates,
- troubleshooting empty data, query errors, or missing dashboards,
- release preparation from `dev` to `main`.

## Core principles
- `dev` is the active development branch.
- `main` is the production branch.
- Data updates must follow the official API flow: upload -> process -> commit.
- Active databases are year-based: `desa_db/dbs/data_<year>.duckdb`.
- Do not commit `.env` or `.duckdb` without explicit data release approval.

## Language policy
- Use English for implementation work, code-related explanations, and development instructions.
- Prefer terminology already established in this codebase when it improves consistency.
- For executive dashboard user-facing narrative content, use Indonesian.
- Keep code syntax, identifiers, and technical notes in English.

## Code Explanation Standard
- Add developer-friendly explanation comments for important frontend sections, especially public dashboard templates such as `front_end/templates/home.html`.
- Explain major HTML blocks by naming their purpose, data source, static-versus-dynamic responsibility, and user task supported.
- Explain major JavaScript or Alpine.js blocks that manage state, computed data, async fetches, dropdown filters, localStorage, cookies, caching, formatting, or backend payload rendering.
- Keep comments in simple technical English so junior and mid-level developers can follow the file without needing extra handoff notes.
- Focus comments on purpose, backend data source, state flow, UI impact, and non-obvious reasoning.
- Avoid noisy line-by-line comments or comments that only repeat what the code already says.
- Preserve this explanation style when adding new features to `home.html` and related dashboard files.

## Quick workflow
1. Confirm your working branch is `dev`.
2. Run the local stack with `docker compose up -d --build` and rebuild on every change.
3. Apply code changes or data updates.
4. Run minimum validation:
   - login/logout,
   - target-year query endpoints,
   - recommendation and IKU dashboards,
   - backend logs without `database does not exist`.
5. Prepare PR from `dev` to `main` following the active team release process.

## Data update SOP (short)
1. `POST /upload/init/{year}`
2. `POST /upload/chunk/{year}`
3. `POST /upload/finalize/{year}`
4. `POST /preview_excel/{year}`
5. `POST /analyze_header/{year}`
6. `POST /process_excel/{year}`
7. Commit data through admin/backend flow, then verify query and dashboard outputs.

## Quick troubleshooting
- UI shows `No Rows To Show`: check whether `data_<year>.duckdb` exists.
- Dashboard/query returns 500: check backend logs, usually year-to-database mismatch.
- One year fails while another works: the database file for that year is likely missing.

## References
- Full technical reference: `references/development-reference.md`
- One-page operations runbook: `/documentation/ONE_PAGE_OPERATIONS_RUNBOOK.md`
