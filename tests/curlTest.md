# Get top 100 rows
```
curl 'http://localhost:8000/query/2025?limit=100'

```
# Filter by a specific column
```
curl 'http://localhost:8000/query/2025?filter_col=Provinsi&filter_val=Java'

```

```
curl -X 'POST' \
         'http://localhost:8000/upload/2025' \
         -H 'accept: application/json' \
         -H 'Content-Type: multipart/form-data' \
         -F 'file=@/path/to/data_skor.xlsb'

```
