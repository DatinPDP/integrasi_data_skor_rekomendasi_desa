import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from jose import jwt, JWTError

app = FastAPI()

# Config
# MUST MATCH auth.py
# CHECK: CHANGE THIS TO A RANDOM STRING FOR PROD!
SECRET_KEY = "CHANGE_ME_TO_SOMETHING_SUPER_SECRET_AND_LONG" 
ALGORITHM = "HS256"

# Setup Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
templates = Jinja2Templates(directory=TEMPLATE_DIR)

# Points to your Data API
# IMPORTANT: You must set this ENV VAR to your Cloudflare Backend URL
# Example: "https://xxx.trycloudflare.com"
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

@app.exception_handler(404)
async def custom_404_handler(request, exc):
    # This serves templates/404.html whenever a page is not found on Port 8001
    return FileResponse(os.path.join(TEMPLATE_DIR, "404.html"), status_code=404)

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    # Check if user is ALREADY logged in, redirect to admin if valid
    token = request.cookies.get("session_token")
    if token:
        try:
            jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            return RedirectResponse(url="/admin")
        except JWTError:
            pass # Token invalid, show login page

    #Pass API_BASE_URL to login template
    return templates.TemplateResponse("login.html", {
        "request": request, 
        "api_url": API_BASE_URL
    })

# Logic to check cookie
@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    # Get cookie
    token = request.cookies.get("session_token")
    
    # If no cookie -> redirect immediate
    if not token:
        return RedirectResponse(url="/login")

    # Verify token (checks signature & expiry)
    try:
        jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        # Token is expired or fake -> REDIRECT IMMEDIATE
        # The browser will never receive the Admin HTML
        return RedirectResponse(url="/login")

    # ONLY SERVE HTML IF VALID
    return templates.TemplateResponse("admin.html", {
        "request": request, 
        "api_url": API_BASE_URL
    })

# Logout Route
@app.get("/logout")
async def logout():
    # Just redirect to login, let the client-side API call handle the actual cookie clearing
    return RedirectResponse(url="/login", status_code=303)

@app.get("/")
async def root():
    return RedirectResponse(url="/login")

if __name__ == "__main__":
    import uvicorn
    # Runs on Port 8001 to avoid conflict
    uvicorn.run(app, host="0.0.0.0", port=8001)
