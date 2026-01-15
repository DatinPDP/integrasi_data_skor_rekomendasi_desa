import subprocess
import sys
import time
import os
from pathlib import Path

# ==========================================
# CONFIGURATION
# ==========================================
BACKEND_CMD = [sys.executable, "desa_db/server.py"]
FRONTEND_TYPE = "fastapi"  # Change to "nextjs" when ready

FRONTEND_CONFIGS = {
    "fastapi": {
        "cmd": [sys.executable, "front_end/web.py"],
        "port": 8001,
        "path": "front_end/web.py"
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
    processes = []
    
    try:
        # Start Backend (inherit stdout/stderr for real-time output)
        print("🔧 Backend starting...")
        backend = subprocess.Popen(BACKEND_CMD)
        processes.append(backend)
        time.sleep(1)  # Reduced wait time
        
        # Start Frontend
        print(f"🎨 Frontend starting...\n")
        frontend_cwd = frontend_config.get('cwd', None)
        frontend = subprocess.Popen(frontend_config['cmd'], cwd=frontend_cwd)
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
