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
# IMPORTANT: You must set this ENV VAR to your Cloudflare Backend URL
# Example: "https://xxx.trycloudflare.com"
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    #Pass API_BASE_URL to login template
    return templates.TemplateResponse("login.html", {
        "request": request, 
        "api_url": API_BASE_URL
    })

# Logic to check cookie
@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
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
