# Walkthrough: Sistem Integrasi Data untuk Dashboard Pimpinan

Dokumen ini menjelaskan arsitektur dan alur kerja sistem integrasi data yang dirancang untuk Ditjen PDP. Sistem ini mampu menangani data dari berbagai sumber (internal & eksternal) dengan format beragam, kemudian mengolahnya menjadi visualisasi dashboard yang informatif.

---

## 1. Ringkasan Arsitektur Sistem

Sistem ini menggunakan pendekatan **hybrid architecture** yang menggabungkan:

| Komponen          | Teknologi/Pendekatan          | Fungsi                                                |
|----------         |---------------------          |--------                                               |
| **Data Lake**     | Object Storage                | Menyimpan file mentah (PDF, Excel, CSV) sebagai arsip |
| **ETL Pipeline**  | Script Cleansing + OCR        | Transformasi data ke format standar                   |
| **Database**      | Relational + JSON Flexible    | Manajemen user & struktur data dinamis                |
| **Dashboard**     | Konfigurasi berbasis tabel    | Visualisasi tanpa coding                              |

---

## 2. Alur Logika Sistem (Flowchart)

```mermaid
graph TD
    %% Node Definitions
    Start([Mulai: User Request Data]) --> InputReq[Input Detail Permintaan Data]
    InputReq --> CheckSource{Sumber Data?}

    %% Jalur Internal (File Excel dari Ditjen PDP)
    CheckSource -- Internal Ditjen PDP --> UploadInternal[Upload File Excel <br/>dari Unit Kerja Internal]
    UploadInternal --> FileCheckInt{Validasi Format}
    
    FileCheckInt -- Format Invalid --> ErrorInt[Tolak & Minta Perbaikan]
    //TAG1--jangan tolak mentah2. kasih balik yg perlu perbaikan, yg tdk perlu perbaikan tetap diambil simpan ke temp/ atau session, misal yg perlu perbaikan cmn ada 40 lines imo membantu banget
    ErrorInt --> UploadInternal
    
    FileCheckInt -- Format Valid --> StoreRawInt[Simpan File Mentah <br/> di Data Lake]
    StoreRawInt --> ProcessETLInt[Proses ETL / Parsing]
    ProcessETLInt --> CleanInternal[Script Cleansing Row/Col]
    CleanInternal --> ReviewInternal[Review Data Sementara]
    ReviewInternal --> ApprovalInt{Verifikasi Data?}
    ApprovalInt -- Revisi --> UploadInternal
    ApprovalInt -- OK --> MapData[Mapping ke Format Standar]

    %% Jalur Eksternal
    CheckSource -- Eksternal / File Lain --> UploadUI[Upload File <br/>PDF / Excel / CSV]
    //TAG2-- PDF mayan rumit, oke kalo isinya ada text & format bener tapi klo isinya bitmap gambar semua gaakan bisa.
    UploadUI --> FileCheck{Validasi Format}
    
    FileCheck -- Format Invalid --> Error[Tolak & Minta Perbaikan]
    //TAG1
    Error --> UploadUI
    
    FileCheck -- Format Valid --> StoreRaw[Simpan File Mentah <br/> di Data Lake]
    StoreRaw --> ProcessETL[Proses ETL / Parsing]
    
    %% Sub-Process ETL Eksternal
    ProcessETL --> DetectType{Tipe File?}
    DetectType -- Excel/CSV --> CleanExcel[Script Cleansing Row/Col]
    DetectType -- PDF/Img --> OCR[OCR & Table Extraction]
    //TAG2
    
    CleanExcel --> ReviewData[Review Data Sementara]
    OCR --> ReviewData
    
    %% Convergence Eksternal
    ReviewData --> Approval{Verifikasi Data?}
    Approval -- Revisi --> UploadUI
    Approval -- OK --> MapData

    %% Final Stage
    MapData --> StoreDB[(Simpan ke Database)]
    StoreDB --> StoreWarehouse[(Data Warehouse Terpusat)]
    StoreWarehouse --> BuildDash[Generate Visualisasi]
    BuildDash --> End([Tampil di Dashboard Pimpinan])

    %% Styling
    classDef database fill:#e1f5fe,stroke:#01579b,stroke-width:2px;
    classDef decision fill:#fff9c4,stroke:#fbc02d,stroke-width:2px;
    classDef process fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px;
    
    class StoreDB,StoreWarehouse,StoreRaw,StoreRawInt database;
    class CheckSource,FileCheck,FileCheckInt,DetectType,Approval,ApprovalInt decision;
    class ProcessETL,ProcessETLInt,CleanExcel,CleanInternal,OCR,MapData process;
```

### 2.1 Penjelasan Tahapan Utama

#### Fase 1: Penerimaan Permintaan
1. **User Request Data** - Pimpinan atau staff mengajukan permintaan data
2. **Input Detail Permintaan** - Sistem mencatat kebutuhan spesifik (periode, wilayah, kategori)
3. **Penentuan Sumber** - Sistem mengidentifikasi apakah data tersedia internal atau perlu input eksternal

#### Fase 2: Pengambilan Data

````carousel
**Jalur Internal (File Excel dari Unit Kerja)**
- Unit kerja internal upload file Excel
- Validasi format file dilakukan otomatis
- File mentah disimpan di Data Lake sebagai arsip
//TAG3-- dibahas lagi, kayanya compressed csv tapi di versioning
- Proses ETL (cleansing row/column) diperlukan
- Review & verifikasi sebelum masuk database

<!-- slide -->

**Jalur Eksternal (Upload File dari Luar)**
- User upload file PDF/Excel/CSV dari sumber eksternal
- Validasi format dilakukan secara otomatis
- File mentah disimpan di Data Lake sebagai arsip
//TAG3
- Proses ETL dengan deteksi tipe file (Excel → Cleansing, PDF → OCR)
- Review & verifikasi sebelum masuk database
````

#### Fase 3: Proses ETL (Extract, Transform, Load)

| Tipe File | Proses | Output |
|-----------|--------|--------|
| **Excel/CSV** | Script Cleansing (hapus row kosong, normalisasi kolom) | Data tabular bersih |
| **PDF/Image** | OCR + Table Extraction | Data tabular dari scan dokumen |

#### Fase 4: Human-in-the-Loop Verification

> [!IMPORTANT]
> **Mengapa Verifikasi Manual Diperlukan?**
> 
> Data eksternal (terutama PDF scan) seringkali mengandung noise atau kesalahan OCR. Tahap **Review Data Sementara** memastikan prinsip **GIGO (Garbage In, Garbage Out)** tidak terjadi.

Alur verifikasi:
- ✅ **OK** → Data lanjut ke mapping format standar
- ⚠️ **Revisi** → User diminta upload ulang atau koreksi manual

#### Fase 5: Penyimpanan & Visualisasi
1. Data yang sudah bersih di-mapping ke format standar
2. Disimpan di **Data Warehouse Terpusat**
3. Dashboard otomatis generate visualisasi berdasarkan konfigurasi

---

## 3. Entity Relationship Diagram (ERD)

```mermaid
erDiagram
    %% User Management
    USERS {
        int user_id PK
        string username
        string role "Admin, Staff, Pimpinan"
        string unit_kerja
    }

    %% Manajemen Permintaan Data
    DATA_REQUESTS {
        int request_id PK
        int user_id FK
        string judul_permintaan
        date tanggal_request
        string status "Pending, Processed, Completed"
        text deskripsi_kebutuhan
    }

    %% Sumber Data & File Mentah
    DATA_SOURCES {
        int source_id PK
        int request_id FK
        string tipe_sumber "INTERNAL_DB, EXTERNAL_FILE"
        string nama_sumber "Misal: Laporan Kab. Bogor"
        string file_path "Link ke Data Lake"
        datetime uploaded_at
    }

    %% Struktur Data Dinamis (Metadata)
    DATASET_METADATA {
        int dataset_id PK
        int source_id FK
        string nama_dataset
        string periode_data "2024, Q1 2025"
        string wilayah "Prov/Kab/Desa"
        string kategori "BUMDes, Dana Desa, dll"
    }

    %% Penyimpanan Nilai Data (Fleksibel)
    DATA_VALUES {
        bigint value_id PK
        int dataset_id FK
        string label_kunci "Misal: Jumlah Penduduk"
        float nilai_angka "Data kuantitatif"
        string nilai_teks "Data kualitatif"
        jsonb detail_attributes "Data tambahan JSON"
    }

    %% Dashboard Configuration
    DASHBOARD_CONFIG {
        int widget_id PK
        int dataset_id FK
        string tipe_chart "Bar, Pie, Map"
        string judul_widget
        string sumbu_x
        string sumbu_y
    }

    %% Relationships
    USERS ||--o{ DATA_REQUESTS : creates
    DATA_REQUESTS ||--|{ DATA_SOURCES : has
    DATA_SOURCES ||--|{ DATASET_METADATA : generates
    DATASET_METADATA ||--|{ DATA_VALUES : contains
    DATASET_METADATA ||--o{ DASHBOARD_CONFIG : visualized_by
```

### 3.1 Penjelasan Struktur Tabel

#### Tabel Manajemen User & Request

| Tabel | Fungsi | Contoh Data |
|-------|--------|-------------|
| `USERS` | Menyimpan data pengguna sistem | Admin, Staff Kecamatan, Pimpinan |
| `DATA_REQUESTS` | Log permintaan data dari user | "Laporan BUMDes Q3 2024" |

#### Tabel Sumber Data

**`DATA_SOURCES`** - Mencatat asal data

```
┌─────────────────────────────────────────────────────────────┐
│  tipe_sumber: INTERNAL_DB                                   │
│  → Menyimpan query log ke database internal                 │
├─────────────────────────────────────────────────────────────┤
│  tipe_sumber: EXTERNAL_FILE                                 │
│  → Menyimpan path file di Data Lake (PDF/Excel asli)        │
│  → Berguna untuk audit trail & verifikasi ulang             │
└─────────────────────────────────────────────────────────────┘
```

#### Tabel Struktur Data Dinamis

> [!TIP]
> **Mengapa Menggunakan Struktur Fleksibel?**
> 
> Format data dari berbagai daerah seringkali tidak konsisten. Dengan pendekatan **EAV (Entity-Attribute-Value)** pada tabel `DATA_VALUES`, sistem dapat menerima format yang berubah-ubah tanpa perlu `ALTER TABLE`.

**`DATA_VALUES`** - Kunci fleksibilitas sistem

| Kolom | Penggunaan |
|-------|------------|
| `label_kunci` | Nama field dinamis (contoh: "Jumlah Petani", "Total Dana Desa") |
| `nilai_angka` | Untuk data kuantitatif |
| `nilai_teks` | Untuk data kualitatif |
| `detail_attributes` | **JSON column** untuk struktur kompleks/nested |

**Contoh penggunaan `detail_attributes`:**

```json
{
  "breakdown_per_desa": [
    {"nama_desa": "Sukamaju", "jumlah": 150},
    {"nama_desa": "Cibadak", "jumlah": 230}
  ],
  "catatan": "Data per Desember 2024",
  "sumber_asli": "Laporan Camat"
}
```

#### Tabel Konfigurasi Dashboard

**`DASHBOARD_CONFIG`** - Self-service visualization

> [!NOTE]
> Admin dapat mengatur tampilan dashboard **tanpa coding**. Cukup pilih dataset, tentukan tipe chart, dan atur sumbu X/Y.

---

## 4. Keunggulan Arsitektur

### 4.1 Data Governance

| Aspek | Implementasi |
|-------|-------------|
| **Audit Trail** | File mentah (PDF asli) tersimpan di Data Lake |
| **Data Quality** | Human-in-the-loop verification sebelum masuk warehouse |
| **Traceability** | Setiap data terhubung ke `request_id` dan `source_id` |

### 4.2 Skalabilitas

```
┌─────────────────────────────────────────────────────────────┐
│  Format Baru Masuk?                                         │
│  ───────────────────                                        │
│  ✅ Tidak perlu ALTER TABLE                                 │
│  ✅ Cukup mapping ke label_kunci baru                       │
│  ✅ Gunakan detail_attributes untuk struktur kompleks       │
└─────────────────────────────────────────────────────────────┘
```

### 4.3 User Experience

- **Untuk Staff**: Upload file dengan validasi otomatis
- **Untuk Admin**: Konfigurasi dashboard via UI
- **Untuk Pimpinan**: Dashboard real-time yang informatif

---

## 5. Teknologi yang Direkomendasikan

| Layer | Opsi Teknologi |
|-------|---------------|
| **Data Lake** | MinIO, AWS S3, Azure Blob |
| **Database** | PostgreSQL (dengan JSONB support) |
| **ETL** | Apache Airflow, Prefect, atau script Python |
| **OCR** | Tesseract, Adobe PDF Extract, AWS Textract |
| **Dashboard** | Metabase, Apache Superset, atau custom web app |
| **Backend API** | Laravel, FastAPI, atau NestJS |

---

## 6. Langkah Implementasi Selanjutnya

- [ ] Setup infrastruktur Data Lake
- [ ] Implementasi database schema (PostgreSQL)
- [ ] Develop upload & validation module
- [ ] Setup ETL pipeline untuk Excel/CSV
- [ ] Integrasi OCR untuk PDF processing
- [ ] Build review & approval workflow
- [ ] Develop dashboard configuration UI
- [ ] Testing end-to-end dengan data riil
- [ ] Deploy ke production environment

---

> [!CAUTION]
> **Perhatian untuk Tim Development**
> 
> Pastikan implementasi `detail_attributes` (JSONB) memiliki **indexing yang tepat** untuk performa query yang optimal, terutama jika volume data besar.
