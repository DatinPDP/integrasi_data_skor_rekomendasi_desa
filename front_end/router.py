import os
import json
import glob
import markdown
import urllib.request
import urllib.parse
import traceback
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from jose import jwt, JWTError
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

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

# Slowapi config
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Markdown Viewer config
DOC_IMAGES_DIR = os.path.join(BASE_DIR, "../documentation/images")
os.makedirs(DOC_IMAGES_DIR, exist_ok=True)
app.mount("/docs_images", StaticFiles(directory=DOC_IMAGES_DIR), name="docs_images")

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
@limiter.limit("20/minute")
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
        with urllib.request.urlopen(req, timeout=5) as response:
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
    # If they click Login from home.html, the existing /login route will
    # intercept the valid session_token and redirect them automatically.

    return templates.TemplateResponse("home.html", {
        "request": request,
        "api_url": ""
    })

# Markdown Viewer Documentation Route
@app.get("/documentation", response_class=HTMLResponse)
async def view_documentation(request: Request, lang: str = "EN"):
    token = request.cookies.get("session_token")
    if not token:
        return RedirectResponse(url="/login")

    try:
        role = get_current_user_role(token)
    except Exception as e:
        role = "admin"

    if role != "admin":
        return RedirectResponse(url="/user")

    # Dependency Check
    try:
        import markdown
    except ImportError as e:
        return HTMLResponse(f"<h1>Dependency Error</h1><p>Failed to import markdown module: {e}</p><p>Ensure 'markdown' is installed in the frontend container.</p>")

    # Path Resolution Check
    try:
        docs_dir = os.path.abspath(os.path.join(BASE_DIR, "../documentation"))
        if not os.path.exists(docs_dir):
             return HTMLResponse(f"<h1>Directory Error</h1><p>Path not found: {docs_dir}</p><p>Verify that your docker-compose.yml mounts the documentation folder into the frontend container.</p>")
        
        prefix = "INDONESIAN" if lang == "ID" else "ENGLISH"
        files = glob.glob(os.path.join(docs_dir, f"{prefix}*.md"))
        
        if not files:
            md_content = f"# {prefix} document not found in {docs_dir}"
        else:
            latest_doc = max(files, key=os.path.getmtime)
            with open(latest_doc, "r", encoding="utf-8") as f:
                md_content = f.read()
    except Exception as e:
        error_trace = traceback.format_exc()
        return HTMLResponse(f"<h1>File Access Error</h1><pre style='background:#f4f4f4; padding:10px; color:red;'>{error_trace}</pre>")

    # Render Markdown Check
    try:
        html_body = markdown.markdown(md_content, extensions=['fenced_code', 'tables'])
    except Exception as e:
        error_trace = traceback.format_exc()
        return HTMLResponse(f"<h1>Markdown Parsing Error</h1><pre style='background:#f4f4f4; padding:10px; color:red;'>{error_trace}</pre>")

    # Output
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en" class="dark">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Documentation Reader</title>
        <script type="module">
            import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
            mermaid.initialize({{ startOnLoad: false, theme: 'neutral' }});
            mermaid.run({{ nodes: document.querySelectorAll('pre code.language-mermaid') }}).catch(err => console.error(err));
            
            window.toggleTheme = function() {{
                document.documentElement.classList.toggle('dark');
            }}
        </script>
        <style>
            /* Firefox Reader View - Monospace Edition */
            :root {{
                --bg: #F9F9FB;
                --text: #333333;
                --text-light: #555555;
                --link: #0060DF;
                --border: #D7D7DB;
                --code-bg: #EDEDF0;
                --nav-bg: #F0F0F4;
            }}
            html.dark {{
                --bg: #202023;
                --text: #FBFBFE;
                --text-light: #AAAAAA;
                --link: #8CB4FF;
                --border: #4A4A4F;
                --code-bg: #2A2A2E;
                --nav-bg: #1C1C1F;
            }}

            body {{
                background-color: var(--bg);
                color: var(--text);
                font-family: Consolas, Monaco, 'Courier New', monospace;
                font-size: 18px;
                line-height: 1.6;
                margin: 0;
                padding: 4rem 1rem 4rem 1rem; /* Top padding clears the fixed nav */
                transition: background-color 0.2s, color 0.2s;
            }}

            .reader-container {{
                max-width: 800px;
                margin: 0 auto;
            }}

            /* Typographic Hierarchy */
            h1, h2, h3, h4 {{ color: var(--text); font-weight: bold; line-height: 1.2; }}
            h1 {{ font-size: 2.2em; margin: 0 0 1.5rem 0; border-bottom: 2px solid var(--border); padding-bottom: 0.3em; }}
            h2 {{ font-size: 1.6em; margin: 2.5rem 0 1rem 0; border-bottom: 1px solid var(--border); padding-bottom: 0.2em; }}
            h3 {{ font-size: 1.3em; margin: 2rem 0 1rem 0; }}
            h4 {{ font-size: 1.1em; margin: 1.5rem 0 0.8rem 0; text-decoration: underline; }}

            p {{ margin: 0 0 1.5rem 0; }}

            /* Lists formatting restored */
            ul {{ list-style-type: disc; margin: 0 0 1.5rem 2.5rem; padding: 0; }}
            ol {{ list-style-type: decimal; margin: 0 0 1.5rem 2.5rem; padding: 0; }}
            li {{ margin-bottom: 0.5rem; padding-left: 0.3rem; }}
            li p {{ margin-bottom: 0.5rem; }}

            a {{ color: var(--link); text-decoration: none; border-bottom: 1px dashed var(--link); }}
            a:hover {{ border-bottom-style: solid; }}

            /* Code block formatting */
            code {{ background-color: var(--code-bg); padding: 0.2em 0.4em; border-radius: 4px; font-size: 0.9em; }}
            pre {{ background-color: var(--code-bg); padding: 1.5rem; border-radius: 6px; border: 1px solid var(--border); overflow-x: auto; margin: 0 0 1.5rem 0; }}
            pre code {{ background-color: transparent; padding: 0; border: none; font-size: 0.85em; }}

            /* Elements */
            table {{ width: 100%; border-collapse: collapse; margin-bottom: 1.5rem; font-size: 0.9em; }}
            th, td {{ border: 1px solid var(--border); padding: 0.8rem; text-align: left; }}
            th {{ background-color: var(--code-bg); font-weight: bold; }}
            
            img {{ max-width: 100%; height: auto; display: block; margin: 2rem auto; border: 1px solid var(--border); border-radius: 4px; }}
            blockquote {{ border-left: 4px solid var(--border); padding-left: 1.5rem; color: var(--text-light); margin: 0 0 1.5rem 0; font-style: italic; }}

            /* Fixed Minimal Navigation Bar */
            .nav-bar {{
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                background-color: var(--nav-bg);
                border-bottom: 1px solid var(--border);
                display: flex;
                justify-content: flex-end;
                align-items: center;
                padding: 0.5rem 2rem;
                z-index: 100;
            }}
            .nav-btn {{
                background: transparent;
                color: var(--text);
                border: 1px solid var(--border);
                padding: 0.3rem 0.8rem;
                margin-left: 0.5rem;
                border-radius: 4px;
                font-family: inherit;
                font-size: 0.85rem;
                cursor: pointer;
                text-decoration: none;
            }}
            .nav-btn:hover {{ background-color: var(--code-bg); border-bottom-style: solid; }}
            .nav-btn.danger {{ color: #d73a49; border-color: #d73a49; border-bottom-style: solid; }}
            .nav-btn.danger:hover {{ background-color: #d73a49; color: white; }}
            html.dark .nav-btn.danger {{ color: #ff7b72; border-color: #ff7b72; }}
            html.dark .nav-btn.danger:hover {{ background-color: #ff7b72; color: #000; }}
        </style>
    </head>
    <body>
        <div class="nav-bar">
            <button onclick="toggleTheme()" class="nav-btn">Theme</button>
            <a href="/documentation?lang=EN" class="nav-btn" title="English">EN</a>
            <a href="/documentation?lang=ID" class="nav-btn" title="Indonesian">ID</a>
            <a href="/admin" class="nav-btn danger">Exit</a>
        </div>

        <div class="reader-container">
            {html_body}
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

if __name__ == "__main__":
    import uvicorn
    # Runs on Port 8001 to avoid conflict
    uvicorn.run(app, host="0.0.0.0", port=8001)
