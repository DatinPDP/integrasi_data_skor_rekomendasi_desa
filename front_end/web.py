import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# Setup Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
templates = Jinja2Templates(directory=TEMPLATE_DIR)

# Points to your Data API
API_BASE_URL = "http://localhost:8000"

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

# Logic to check cookie
@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    # Simple Cookie Check
    auth_token = request.cookies.get("session_token")
    if auth_token != "admin_secret_123":
        return RedirectResponse(url="/login", status_code=302)

    return templates.TemplateResponse("admin.html", {
        "request": request, 
        "api_url": API_BASE_URL
    })

# Logout Route
@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(
        key="session_token",
        path="/",
        httponly=True,
        secure=False,
        samesite="strict"
    )
    # Optional: prevent caching
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response

@app.get("/")
async def root():
    return RedirectResponse(url="/login")

if __name__ == "__main__":
    import uvicorn
    # Runs on Port 8001 to avoid conflict
    uvicorn.run(app, host="0.0.0.0", port=8001)
