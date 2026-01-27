import json
import os
import sys
import bcrypt
 
# Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(BASE_DIR, ".config")
AUTH_FILE = os.path.join(CONFIG_DIR, "auth_users.json")
 
def load_users():
    if not os.path.exists(AUTH_FILE):
        return {}
    with open(AUTH_FILE, "r") as f:
        return json.load(f)
 
def save_users(data):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(AUTH_FILE, "w") as f:
        json.dump(data, f, indent=4)
 
def add_user(username, password, role="admin"):
    users = load_users()
 
    # Hash the password using native bcrypt
    # 1. Encode password to bytes
    # 2. Generate salt and hash
    hashed_bytes = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    # 3. Decode back to string for storage in JSON
    hashed_str = hashed_bytes.decode('utf-8')
 
    users[username] = {
        "hash": hashed_str,
        "role": role,
        "active": True
    }
 
    save_users(users)
    print(f"✅ User '{username}' added/updated successfully.")
 
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python add_user.py <username> <password> [role]")
        print("Example: python add_user.py admin MySecretPass123 admin")
    else:
        u = sys.argv[1]
        p = sys.argv[2]
        r = sys.argv[3] if len(sys.argv) > 3 else "admin"
        add_user(u, p, r)
