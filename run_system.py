import subprocess
import sys
import time
import os
import signal

# Configuration
# 1. Backend (Data API) -> Port 8000
# 2. Frontend (HTML Serving) -> Port 8001
# Later, you can change FRONTEND_CMD to: ["npm", "run", "start"] for Next.js
BACKEND_CMD = [sys.executable, "desa_db/server.py"]
FRONTEND_CMD = [sys.executable, "front_end/web.py"]

def main():
    print("🚀 Starting System...")
    
    # 1. Start Backend (API)
    print("   └── Starting Backend (Port 8000)...")
    backend = subprocess.Popen(BACKEND_CMD, cwd=os.getcwd())
    
    # Wait a second for DB to init
    time.sleep(2)
    
    # 2. Start Frontend (UI)
    print("   └── Starting Frontend (Port 8001)...")
    frontend = subprocess.Popen(FRONTEND_CMD, cwd=os.getcwd())
    
    print("\n✅ System Running!")
    print("   👉 Admin Dashboard: http://localhost:8001/admin")
    print("   👉 Login Page:      http://localhost:8001/login")
    print("   (Press Ctrl+C to stop)\n")

    try:
        backend.wait()
        frontend.wait()
    except KeyboardInterrupt:
        print("\n🛑 Stopping services...")
        backend.terminate()
        frontend.terminate()
        sys.exit(0)

if __name__ == "__main__":
    main()
