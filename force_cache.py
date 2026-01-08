import sys
import os

# 1. Setup paths so Python can find 'desa_db'
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(current_dir, "desa_db"))

# 2. Import the cache function
from desa_db.server import refresh_filter_cache

if __name__ == "__main__":
    print("🔄 Force generating cache for 2025...")
    
    # This reads the existing DuckDB and writes the JSON file
    refresh_filter_cache("2025")
    
    print("✅ Done! Check .config/ folder.")
