# Skill: Acuan Pengembangan Sistem Informasi Ditjen PDP

## 1. Tujuan
Dokumen ini adalah acuan kerja praktis untuk pengembangan dan operasional proyek `integrasi_data_skor_rekomendasi_desa`, disusun dari:

- Dokumentasi sistem: `Dokumentasi_Sistem_Informasi_Ditjen_PDP_improvised.docx`
- Struktur dan implementasi aktual repository (backend, frontend, docker, config)

Fokus utamanya:

- konsistensi arsitektur,
- keamanan akses,
- alur update data yang benar,
- kualitas rilis dari `dev` ke `main`.

---

## 2. Ruang Lingkup Sistem
Sistem memproses data desa untuk menghasilkan:

- grid data terintegrasi,
- dashboard rekomendasi,
- dashboard IKU,
- ekspor Excel pelaporan.

Komponen inti:

- `backend`: FastAPI (`desa_db/server.py`) untuk API, upload, proses data, query, dashboard.
- `frontend`: FastAPI router (`front_end/router.py`) + template HTML (admin/user/login).
- `nginx`: reverse proxy, entry point publik `:8080`.
- `backup`: job backup basis data berkala.

---

## 3. Konvensi Branch dan Rilis
- `dev` = branch pengembangan aktif.
- `main` = branch produksi (yang ditampilkan ke pengguna website).

Aturan kerja:

1. Semua perubahan fitur/fix dikerjakan di `dev`.
2. Uji lokal + validasi endpoint dilakukan di `dev`.
3. Promosi ke `main` melalui PR/merge terkontrol.
4. Hindari commit langsung ke `main`.

---

## 4. Struktur Konfigurasi Penting
Semua konfigurasi inti ada di `.config/`:

- `auth_users.json`: user, hash password, role, active.
- `headers.json`: standardisasi alias header kolom input.
- `rekomendasi.json`: logika mapping skor -> label rekomendasi.
- `table_structure.csv`: struktur dashboard rekomendasi.
- `table_structure_IKU.csv`: struktur dashboard IKU.
- `iku_mapping.json`: mapping parent IKU ke kolom skor.
- `intervensi_kegiatan_mapping.json`: mapping intervensi/kegiatan.

Prinsip:

- Perubahan konfigurasi = perubahan perilaku sistem.
- Update konfigurasi harus diuji bersama endpoint query/dashboard.

---

## 5. Keamanan dan Autentikasi
Model keamanan:

- Login via `/api/login`, logout via `/api/logout`.
- Sesi menggunakan JWT pada cookie `HttpOnly`.
- `APP_SECRET_KEY` wajib ada di `.env`.
- Endpoint upload/proses data bersifat admin-only.

Checklist minimum:

1. `APP_SECRET_KEY` tersedia dan kuat.
2. User admin dibuat via `add_user.py`.
3. Cookie dan role-based access tidak dinonaktifkan di production.

---

## 6. SOP Update Data (WAJIB)
Update data mengikuti pipeline upload-proses-commit, bukan edit manual tabel.

### 6.1 Alur resmi (sesuai dokumentasi)
1. Upload file data (resumable):
   - `POST /upload/init/{year}`
   - `POST /upload/chunk/{year}`
   - `POST /upload/finalize/{year}`
2. Validasi dan pemetaan:
   - `POST /preview_excel/{year}`
   - `POST /analyze_header/{year}`
3. Proses:
   - `POST /process_excel/{year}`
4. Commit ke database dan verifikasi:
   - commit data (alur backend/admin)
   - cek query/dashboard/history endpoint.

### 6.2 Praktik operasional di proyek ini
Database aktif dibaca per tahun dari:

- `desa_db/dbs/data_<year>.duckdb`

Jika UI menampilkan `No Rows To Show` atau error 500 tahun tertentu:

1. Pastikan file `data_<year>.duckdb` ada.
2. Cek log backend untuk error `database does not exist`.
3. Pastikan tahun yang dipilih di UI sesuai file DB yang tersedia.

### 6.3 Status update data saat ini
Perbaikan data lokal sudah dilakukan:

- file `data_2025.duckdb` dipulihkan ke `desa_db/dbs/`
- verifikasi isi: tabel `master_data` terdeteksi dengan `12600` baris
- endpoint publik 2025 merespons `200 OK`

Catatan:

- Tahun 2026 akan gagal jika `data_2026.duckdb` belum tersedia.

---

## 7. SOP Menjalankan Sistem Lokal
Prasyarat:

- Docker Desktop aktif
- `.env` berisi `APP_SECRET_KEY`

Jalankan:

```bash
docker compose up -d --build
docker compose ps
```

Akses:

- `http://127.0.0.1:8080`

Aturan wajib:

- Gunakan `docker compose up -d --build` secara eksklusif.
- Lakukan rebuild pada setiap perubahan agar artefak backend/frontend/nginx tetap sinkron.

---

## 8. Endpoint Kritis untuk Validasi Pasca-Update
Lakukan smoke test minimum:

- Auth:
  - `POST /api/login`
  - `POST /api/logout`
- Data/update:
  - `/upload/init/{year}`
  - `/upload/chunk/{year}`
  - `/upload/finalize/{year}`
  - `/preview_excel/{year}`
  - `/analyze_header/{year}`
  - `/process_excel/{year}`
- Konsumsi data:
  - `/query/{year}`
  - endpoint dashboard terkait tahun aktif
  - endpoint history/versions terkait tahun aktif

---

## 9. Checklist QA Sebelum Merge ke `main`
1. Container `backend`, `frontend`, `nginx`, `backup` status `Up`.
2. Login admin berhasil.
3. Query data tahun target tidak 500.
4. Dashboard rekomendasi + IKU tampil.
5. Ekspor Excel berjalan.
6. Tidak ada error `database does not exist` pada log backend.
7. Tidak ada secret/DB file sensitif ikut commit.

---

## 10. Larangan dan Batasan
- Jangan commit `.env`.
- Jangan commit file `.duckdb` tanpa keputusan rilis data yang jelas.
- Jangan ubah struktur `.config/*` tanpa uji dashboard/query.
- Jangan mendorong perubahan langsung ke `main`.

---

## 11. Referensi File Implementasi
- Backend API: `desa_db/server.py`
- Middleware data/report: `desa_db/middleware.py`
- Auth: `desa_db/auth.py`, `add_user.py`
- Frontend router: `front_end/router.py`
- Template UI: `front_end/templates/*.html`
- Infra: `docker-compose.yml`, `Dockerfile`, `nginx.conf`
- Test: `tests/server_test.py`

---

## 12. Keputusan Operasional Ke Depan
Untuk setiap permintaan pengembangan baru:

1. Mulai dari `dev`.
2. Ikuti alur update data resmi (upload -> process -> commit -> verifikasi).
3. Validasi endpoint dan dashboard berdasarkan tahun data yang benar.
4. Promosikan ke `main` hanya saat checklist QA terpenuhi.
