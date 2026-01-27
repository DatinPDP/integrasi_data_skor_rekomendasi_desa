import os
import json
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
import bcrypt

# === CONFIGURATION ===
# CHANGE THIS TO A RANDOM STRING FOR PROD!
SECRET_KEY = "CHANGE_ME_TO_SOMETHING_SUPER_SECRET_AND_LONG" 
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440 # 24 Hours

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Points to .config/auth_users.json sibling to desa_db
AUTH_FILE = os.path.abspath(os.path.join(BASE_DIR, "../.config/auth_users.json"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def auth_get_users_db():
    if not os.path.exists(AUTH_FILE):
        return {}
    try:
        with open(AUTH_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def auth_verify_password(plain_password, hashed_password):
    # Check if plain_password matches the hash
    # Use valid encoding for bcrypt
    return bcrypt.checkpw(
        plain_password.encode('utf-8'), 
        hashed_password.encode('utf-8')
    )

def auth_create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# === THE GATEKEEPER DEPENDENCY ===
async def auth_get_current_user(request: Request):
    """
    Checks for 'session_token' in Cookies.
    If missing or invalid -> Throws 401 Unauthorized.
    """
    token = request.cookies.get("session_token")
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Optional: Check if user still exists/is active in DB
    db = auth_get_users_db()
    user = db.get(username)
    if not user or not user.get("active"):
        raise HTTPException(status_code=401, detail="User inactive or deleted")

    return username
