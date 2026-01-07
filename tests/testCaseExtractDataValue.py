import polars as pl

file_path = "../contohTemplateDashboardSkorRekomendasiID2025.xlsb"
sheet_name = "Skor"
output_file = "filtered_output.csv"

# 1. Read Manual Headers
with open("desa_db\headers.txt", "r") as f:
    manual_headers = [line.strip() for line in f]

# 2. Read Data (No headers)
df = pl.read_excel(
    file_path, 
    sheet_name=sheet_name, 
    engine="calamine",
    read_options={"header_row": None}
)

# 3. Slice Rows: Start from Row 7 (Index 6)
df = df.slice(6, None)

# 4. Slice Columns: Start from Column B (Index 1)
# Column A is index 0. Column B is index 1.
# Column JB is index 261 (Calculation: 10*26 + 2 - 1 = 261).
df = df[:, 1:262]

# 5. FILTER: Clean "Empty" Columns (The logic you provided)
df = df.select([
    col for col in df 
    if not (col.is_null().all() or (col.dtype == pl.String and (col == "").all()))
])

# 6. Regex Filter for ID
pattern = r"[0-9]{10}"
filtered_df = df.filter(
    pl.any_horizontal(
        pl.all().cast(pl.String).str.contains(pattern)
    )
)

# 7. Write Headers Manually, then Append Data
# We use open() to write the header string first, then append the DataFrame.
with open(output_file, "w", encoding="utf-8") as f:
    # Write the manual header line
    f.write("\t".join(manual_headers) + "\n")
    
    # Write the data (include_header=False prevents writing the "column_0, column_1" names)
    filtered_df.write_csv(f, separator="\t", quote_style="never", include_header=False)
