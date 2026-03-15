import os
import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from jose import jwt, JWTError

app = FastAPI(
    docs_url=None, 
    redoc_url=None, 
    openapi_url=None
) 

# Config
# MUST MATCH auth.py
SECRET_KEY = os.getenv("APP_SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("FATAL: APP_SECRET_KEY is not set in environment variables!")
ALGORITHM = "HS256"

# Setup Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
templates = Jinja2Templates(directory=TEMPLATE_DIR)

# Points to your Data API
# IMPORTANT: You must set this ENV VAR to your Cloudflare Backend URL
# Example: "https://xxx.trycloudflare.com"
# old-previous: API_BASE_URL
# uncomment when needed
#API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

# CHANGE 1: Read env var for Docker-to-Docker communication
# Default to localhost for local testing without Docker
API_INTERNAL_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

@app.exception_handler(404)
async def custom_404_handler(request, exc):
    # This serves templates/404.html whenever a page is not found on Port 8001
    return FileResponse(os.path.join(TEMPLATE_DIR, "404.html"), status_code=404)

# --- SECURITY HELPER ---
def get_current_user_role(token: str):
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("role")
    except JWTError:
        return None


@app.get("/login", response_class=HTMLResponse)
async def login_view(request: Request):
    """
    Renders the pure HTML login page.
    Redirects if user is already logged in.
    """
    # If already logged in, redirect immediately
    token = request.cookies.get("session_token")
    if token:
        role = get_current_user_role(token)
        if role == "admin": 
            return RedirectResponse(url="/admin", status_code=302)
        elif role == "user": 
            return RedirectResponse(url="/user", status_code=302)
        # If role is invalid, fall through to login page (token might be bad)

    return templates.TemplateResponse("login.html", {"request": request, "error": None})

# SSR LOGIN HANDLER
@app.post("/login", response_class=HTMLResponse)
async def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    """
    SSR Login Proxy:
    1. Accepts Username/Pass
    2. Calls Backend API
    3. Sets Cookie
    4. Redirects based on Role
    """
    try:
        # Prepare request to Backend API
        # url = f"{API_BASE_URL}/api/login"
        url = f"{API_INTERNAL_URL}/api/login"
        payload = json.dumps({"username": username, "password": password}).encode("utf-8")
        
        req = urllib.request.Request(url, data=payload, headers={
            'Content-Type': 'application/json',
            'User-Agent': 'FastAPI-SSR-Proxy'
        })

        # Execute Request
        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                body = json.loads(response.read().decode())
                
                # Extract Role safely (Default to 'user' for safety)
                user_role = body.get("role", "user")
                
                # Debug print to server console
                # print(f"DEBUG: Login Success. User: {username}, Role: {user_role}")

                # Create Session Token (SSR Side)
                expires = datetime.utcnow() + timedelta(minutes=360)
                to_encode = {"sub": username, "role": user_role, "exp": expires}
                token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

                # Determine Redirect Target
                if user_role == "admin":
                    target_url = "/admin"
                else:
                    target_url = "/user"

                # Build Response
                resp = RedirectResponse(url=target_url, status_code=303)
                
                # Set Secure Cookie
                resp.set_cookie(
                    key="session_token",
                    value=token,
                    httponly=True,
                    samesite="lax", # Lax is better for top-level navigation
                    secure=True # Set True if using HTTPS
                )
                return resp

    except urllib.error.HTTPError as e:
        # Backend returned 401 (Unauthorized) or 403 or 500
        error_msg = "Invalid username or password."
        if e.code == 500: error_msg = "Server Error."
        return templates.TemplateResponse("login.html", {"request": request, "error": error_msg})

    except Exception as e:
        print(f"Login Error: {e}")
        return templates.TemplateResponse("login.html", {"request": request, "error": "Connection error to Backend"})

# Logic to check cookie
@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    token = request.cookies.get("session_token")
    role = get_current_user_role(token)
    
    if not token: return RedirectResponse(url="/login")
    if role != "admin": return RedirectResponse(url="/user") # Force non-admins out

    return templates.TemplateResponse("admin.html", {
        "request": request, 
        # This forces the browser to use relative paths (e.g. "/query/...")
        # which Nginx will correctly route to the backend.
        # API_BASE_URL is for non docker, uncomment when needed
        "api_url": ""
        #"api_url": API_BASE_URL
    })

# Logic to check cookie
@app.get("/user", response_class=HTMLResponse)
async def user_dashboard(request: Request):
    token = request.cookies.get("session_token")
    role = get_current_user_role(token)

    if not token: return RedirectResponse(url="/login")
    

    return templates.TemplateResponse("user.html", {
        "request": request, 
        # API_BASE_URL is for non docker, uncomment when needed
        "api_url": ""
        #"api_url": API_BASE_URL
    })

# Logout Route
@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=302)
    response.delete_cookie("session_token")
    return response

@app.get("/")
async def root(request: Request):
    token = request.cookies.get("session_token")
    role = get_current_user_role(token)
    
    if role == "admin": return RedirectResponse(url="/admin")
    if role == "user": return RedirectResponse(url="/user")
    
    return templates.TemplateResponse("home.html", {
        "request": request,
        "api_url": "" 
    })

if __name__ == "__main__":
    import uvicorn
    # Runs on Port 8001 to avoid conflict
    uvicorn.run(app, host="0.0.0.0", port=8001)
