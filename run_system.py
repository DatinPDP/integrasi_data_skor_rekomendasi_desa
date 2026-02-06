import subprocess
import sys
import time
import os
from pathlib import Path
from dotenv import load_dotenv

# ==========================================
# CONFIGURATION INJECTION
# ==========================================
# 1. Generate a "fake" secret for local dev if missing
if "APP_SECRET_KEY" not in os.environ:
    os.environ["APP_SECRET_KEY"] = "LOCAL_DEV_SECRET_KEY_12345"

# 2. Point Frontend to Localhost Backend (Crucial for the Table fix)
if "API_BASE_URL" not in os.environ:
    os.environ["API_BASE_URL"] = "http://localhost:8000"

# ==========================================
# SYSTEM CONFIG
# ==========================================
BACKEND_CMD = [sys.executable, "desa_db/server.py"]
FRONTEND_TYPE = "fastapi"  # Change to "nextjs" when ready

FRONTEND_CONFIGS = {
    "fastapi": {
        "cmd": [sys.executable, "front_end/router.py"],
        "port": 8001,
        "path": "front_end/router.py"
    },
    "nextjs": {
        "cmd": ["npm", "run", "dev"],
        "port": 3000,
        "path": "frontend/package.json",
        "cwd": "frontend"
    }
}

# ==========================================
# MAIN
# ==========================================
def main():
    load_dotenv()
    frontend_config = FRONTEND_CONFIGS.get(FRONTEND_TYPE)
    
    if not frontend_config:
        print(f"❌ Unknown FRONTEND_TYPE: {FRONTEND_TYPE}")
        sys.exit(1)
    
    # Quick validation
    if not Path(frontend_config['path']).exists():
        print(f"❌ Frontend not found: {frontend_config['path']}")
        if FRONTEND_TYPE == "nextjs":
            print("\n📦 Setup Next.js:")
            print("   npx create-next-app@latest frontend")
        sys.exit(1)
    
    print("🚀 Starting System...\n")
    os.environ["API_BROWSER_URL"] = "http://localhost:8000"
    print(f"🔑 SECRET_KEY: {os.environ['APP_SECRET_KEY']}")
    print(f"🔗 API URL:    {os.environ['API_BASE_URL']}")

    processes = []
    
    try:
        # Start Backend (inherit stdout/stderr for real-time output)
        print("🔧 Backend starting...")
        backend = subprocess.Popen(BACKEND_CMD)
        processes.append(backend)
        time.sleep(2)
        
        # Start Frontend
        print(f"🎨 Frontend starting...\n")
        frontend_cwd = frontend_config.get('cwd', None)
        frontend = subprocess.Popen(frontend_config['cmd'], cwd=frontend_cwd, env=os.environ.copy())
        processes.append(frontend)
        
        # Print URLs immediately (don't wait)
        print("\n" + "="*50)
        print("✅ SYSTEM RUNNING")
        print("="*50)
        print(f"Backend:  http://localhost:8000")
        print(f"Frontend: http://localhost:{frontend_config['port']}")
        if FRONTEND_TYPE == "fastapi":
            print(f"Admin:    http://localhost:{frontend_config['port']}/admin")
        print("\nPress Ctrl+C to stop")
        print("="*50 + "\n")
        
        # Wait for processes
        for proc in processes:
            proc.wait()
            
    except KeyboardInterrupt:
        print("\n\n🛑 Stopping...")
        for proc in processes:
            proc.terminate()
        print("✅ Stopped\n")
        sys.exit(0)

if __name__ == "__main__":
    main()
