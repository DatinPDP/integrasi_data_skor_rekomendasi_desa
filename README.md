# Config
```
/root
/.config/recommendation.json
/.config/headers.txt
```
# Requirements
Python 3.11.9
```bash
pip install -r .config/requirements.txt
```

# Run backend+middleware
```bash
python desa_db/server.py
```
# Run mock frontend
```bash
streamlit run tests/test_serverSheets.py
```

To run the tests for the server, use the following command in your terminal:
```bash
pytest tests/test_server.py
```
