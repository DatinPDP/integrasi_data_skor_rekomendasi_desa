import os
import json
import glob
import markdown
import urllib.request
import urllib.parse
import traceback
import shutil
import time
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse
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

# Config Editor Settings
CONFIG_DIR = os.path.abspath(os.path.join(BASE_DIR, "../.config"))
HISTORY_DIR = os.path.join(CONFIG_DIR, ".history")
os.makedirs(HISTORY_DIR, exist_ok=True)

ALLOWED_CONFIG_FILES = [
    "headers.json", "iku_mapping.json", "intervensi_kegiatan_mapping.json",
    "rekomendasi.json", "table_structure.csv", "table_structure_IKU.csv"
]

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
        html_body = markdown.markdown(md_content, extensions=['fenced_code', 'tables', 'toc'])
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
        <title>Documentation</title>
        <script type="module">
            import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
            mermaid.initialize({{ startOnLoad: false, theme: 'neutral' }});
            mermaid.run({{ nodes: document.querySelectorAll('pre code.language-mermaid') }}).catch(console.error);
            window.toggleTheme = () => document.documentElement.classList.toggle('dark');
        </script>
        <style>
            :root {{ --bg:#F9F9FB; --txt:#333; --link:#0060DF; --brd:#D7D7DB; --code:#EDEDF0; }}
            html.dark {{ --bg:#202023; --txt:#FBFBFE; --link:#8CB4FF; --brd:#4A4A4F; --code:#2A2A2E; }}
            body {{ background:var(--bg); color:var(--txt); font: 18px/1.6 Consolas, Monaco, monospace;
            margin:0; padding:4rem 1rem; transition:.2s; }}
            .container {{ max-width:800px; margin:0 auto; }}
            h1, h2, h3, h4 {{ font-weight:bold; line-height:1.2; margin:2rem 0 1rem; }}
            h1 {{ font-size:2.2em; border-bottom:2px solid var(--brd); padding-bottom:.3em; margin-top:0; }}
            h2 {{ font-size:1.6em; border-bottom:1px solid var(--brd); padding-bottom:.2em; }}
            h3 {{ font-size:1.3em; }}
            h4 {{ font-size:1.1em; text-decoration:underline; }}
            p, ul, ol, pre, table, blockquote {{ margin:0 0 1.5rem; }}
            ul, ol {{ padding-left:2.5rem; }}
            li {{ margin-bottom:.5rem; }}
            a {{ color:var(--link); text-decoration:none; border-bottom:1px dashed; }}
            a:hover {{ border-bottom-style:solid; }}
            code, pre {{ background:var(--code); border-radius:4px; }}
            code {{ padding:.2em .4em; font-size:.9em; }}
            pre {{ padding:1.5rem; border:1px solid var(--brd); overflow-x:auto; }}
            pre code {{ background:0 0; padding:0; border:none; }}
            table {{ width:100%; border-collapse:collapse; font-size:.9em; }}
            th, td {{ border:1px solid var(--brd); padding:.8rem; text-align:left; }}
            th {{ background:var(--code); }}
            img {{ max-width:100%; display:block; margin:2rem auto; border:1px solid var(--brd); border-radius:4px; }}
            blockquote {{ border-left:4px solid var(--brd); padding-left:1.5rem; opacity:0.8; font-style:italic; }}
            .nav {{ position:fixed; top:0; left:0; right:0; background:transparent; display:flex;
            justify-content:flex-end; padding:.5rem 2rem; z-index:100; pointer-events:none; }}
            .nav-btn {{ background:var(--bg); color:var(--txt); border:1px solid var(--brd); padding:.3rem .8rem;
            margin-left:.5rem; border-radius:4px; font:inherit; font-size:.85rem; cursor:pointer;
            text-decoration:none; pointer-events:auto; }}
            .nav-btn:hover {{ background:var(--code); border-bottom-style:solid; }}
            .nav-btn.danger {{ color:#d73a49; border-color:#d73a49; }}
            .nav-btn.danger:hover {{ background:#d73a49; color:#fff; }}
            html.dark .nav-btn.danger {{ color:#ff7b72; border-color:#ff7b72; }}
            html.dark .nav-btn.danger:hover {{ background:#ff7b72; color:#000; }}
        </style>
    </head>
    <body>
        <div class="nav">
            <button onclick="toggleTheme()" class="nav-btn">Theme</button>
            <a href="?lang=EN" class="nav-btn">EN</a>
            <a href="?lang=ID" class="nav-btn">ID</a>
            <a href="/admin" class="nav-btn danger">Exit</a>
        </div>
        <div class="container">
            {html_body}
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/api/config/read")
async def api_read_config(request: Request, filename: str, hist_id: str = ""):
    token = request.cookies.get("session_token")
    if not token or get_current_user_role(token) != "admin": return Response(status_code=403)
    if filename not in ALLOWED_CONFIG_FILES: return Response(status_code=403)

    # Read target file or historical file
    filepath = os.path.join(CONFIG_DIR, filename)
    if hist_id:
        if not hist_id.startswith(filename): return Response(status_code=403)
        filepath = os.path.join(HISTORY_DIR, hist_id)

    content = ""
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f: content = f.read()

    # Get history tree
    hist_pattern = os.path.join(HISTORY_DIR, f"{filename}.*.bak")
    history_files = sorted(glob.glob(hist_pattern), reverse=True)
    history = [{"id": os.path.basename(h), "time": os.path.getmtime(h)} for h in history_files]

    return JSONResponse({"content": content, "history": history})


@app.post("/api/config/save")
async def api_save_config(request: Request, filename: str):
    token = request.cookies.get("session_token")
    if not token or get_current_user_role(token) != "admin": return Response(status_code=403)
    if filename not in ALLOWED_CONFIG_FILES: return Response(status_code=403)

    data = await request.json()
    new_content = data.get("content", "")
    filepath = os.path.join(CONFIG_DIR, filename)

    # Create Undo Tree Backup
    if os.path.exists(filepath):
        ts = int(time.time())
        bak_path = os.path.join(HISTORY_DIR, f"{filename}.{ts}.bak")
        shutil.copy2(filepath, bak_path)

    # Write new file
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)
    return JSONResponse({"status": "success"})

@app.get("/config-editor", response_class=HTMLResponse)
async def view_config_editor(request: Request):
    token = request.cookies.get("session_token")
    if not token: return RedirectResponse(url="/login")
    try: role = get_current_user_role(token)
    except Exception: role = "admin"
    if role != "admin": return RedirectResponse(url="/user")

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Config Editor</title>
        <style>
            :root {{ --bg:#F9F9FB; --bg-sec:#F0F0F4; --txt:#333; --brd:#D7D7DB; --code:#EDEDF0; --hl:#0060DF; }}
            html.dark {{ --bg: #000000; --bg-sec: #16161D; --txt: #DCD7BA; --brd: #363646; --code: #2A2A37; --hl: #7E9CD8; --success: #76946A; --danger: #C34043; }}
            * {{ box-sizing:border-box; font-family:Consolas, monospace; }}
            body {{ background:var(--bg); color:var(--txt); margin:0; display:flex; height:100vh; overflow:hidden; font-size:14px; transition: background 0.2s, color 0.2s; }}
            .sidebar {{ width:20%; min-width:220px; max-width:300px; background:var(--bg-sec); border-right:1px solid var(--brd); display:flex; flex-direction:column; padding:15px; gap:15px; }}
            .sidebar h2 {{ margin:0; font-size:16px; border-bottom:1px solid var(--brd); padding-bottom:10px; }}
            .main {{ flex:1; display:flex; flex-direction:column; width:80%; }}
            .topbar {{ display:flex; justify-content:space-between; align-items:center; padding:10px 20px; border-bottom:1px solid var(--brd); background:var(--bg); }}
            select, button, .btn {{ background:var(--bg); color:var(--txt); border:1px solid var(--brd); padding:6px 12px; border-radius:4px; font:inherit; cursor:pointer; text-decoration:none; }}
            select:hover, button:hover, .btn:hover {{ background:var(--code); }}
            .btn-primary {{ border-color:#28a745; color:#28a745; font-weight:bold; }}
            .btn-danger {{ border-color:#d73a49; color:#d73a49; }}
            html.dark .btn-danger {{ border-color:#ff7b72; color:#ff7b72; }}
            #history-list {{ flex:1; overflow-y:auto; border:1px solid var(--brd); background:var(--bg); border-radius:4px; margin-top:5px; }}
            .hist-item {{ padding:8px 10px; border-bottom:1px solid var(--brd); cursor:pointer; font-size:12px; }}
            .hist-item:hover, .hist-item.active {{ background:var(--code); }}
            .hist-item.active {{ border-left:3px solid var(--hl); }}
            #editor {{ flex:1; overflow:hidden; }}
            .cm-editor {{ height:100%; outline:none !important; }}
        </style>
    </head>
    <body>
        <div class="sidebar">
            <h2>Config Editor</h2>
            <div>
                <label style="font-size:12px; opacity:0.8;">Target File:</label>
                <select id="file-select" style="width:100%; margin-top:5px;">
                    <option value="" disabled selected>-- Select Config --</option>
                    {"".join([f'<option value="{f}">{f}</option>' for f in ALLOWED_CONFIG_FILES])}
                </select>
            </div>
            <div style="flex:1; display:flex; flex-direction:column; min-height:0;">
                <label style="font-size:12px; opacity:0.8;">Undo Tree (History):</label>
                <div id="history-list"></div>
            </div>
        </div>
        <div class="main">
            <div class="topbar">
                <div style="display:flex; align-items:center; gap:15px;">
                    <span id="status-msg" style="font-weight:bold; color:var(--hl);">Ready</span>
                    <span id="file-lbl" style="opacity:0.7; font-size:12px;">No file selected</span>
                </div>
                <div style="display:flex; gap:10px;">
                    <button onclick="document.documentElement.classList.toggle('dark')">Theme</button>
                    <button id="btn-save" class="btn-primary">Save</button>
                    <a href="/admin" class="btn btn-danger">Exit</a>
                </div>
            </div>
            <div id="editor"></div>
        </div>

        <script type="module">
            import {{EditorView, basicSetup}} from "https://esm.sh/codemirror@6.0.1";
            import {{json}} from "https://esm.sh/@codemirror/lang-json@6.0.1";

            const $ = id => document.getElementById(id);
            let view = new EditorView({{ extensions: [basicSetup, json()], parent: $("editor") }});
            let state = {{ file: "", histId: "" }};

            window.loadFile = async (filename, histId = "") => {{
                $("status-msg").textContent = "Loading...";
                let res = await fetch(`/api/config/read?filename=${{filename}}${{histId ? '&hist_id='+histId : ''}}`);
                if (!res.ok) return $("status-msg").textContent = "Error loading";

                let data = await res.json();
                view.dispatch({{ changes: {{from: 0, to: view.state.doc.length, insert: data.content}} }});
                state = {{ file: filename, histId }};

                $("file-lbl").textContent = histId ? `Viewing past: ${{histId}}` : `Live: ${{filename}}`;
                $("status-msg").textContent = histId ? "Unsaved Preview" : "Loaded";
                $("status-msg").style.color = histId ? "#d73a49" : "var(--hl)";

                if (!histId) {{
                    $("history-list").innerHTML = `<div class="hist-item active" onclick="loadFile('${{filename}}')">[Current Live]</div>` +
                        data.history.map(h => `<div id="hist-${{h.id}}" class="hist-item" onclick="loadFile('${{filename}}', '${{h.id}}')">${{new Date(h.time * 1000).toLocaleString()}}</div>`).join('');
                }} else {{
                    document.querySelectorAll('.hist-item').forEach(el => el.classList.remove('active'));
                    $('hist-' + histId)?.classList.add('active');
                }}
            }};
            $("file-select").onchange = e => loadFile(e.target.value);
            $("btn-save").onclick = async () => {{
                if (!state.file || (state.histId && !confirm("Overwrite live file with old backup?"))) return;
                $("status-msg").textContent = "Saving...";
                let res = await fetch(`/api/config/save?filename=${{state.file}}`, {{
                    method: "POST", headers: {{"Content-Type": "application/json"}},
                    body: JSON.stringify({{content: view.state.doc.toString()}})
                }});
                if (res.ok) {{
                    $("status-msg").textContent = "Saved!";
                    $("status-msg").style.color = "#28a745";
                    loadFile(state.file);
                }} else {{
                    $("status-msg").textContent = "Error saving.";
                }}
            }};
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

if __name__ == "__main__":
    import uvicorn
    # Runs on Port 8001 to avoid conflict
    uvicorn.run(app, host="0.0.0.0", port=8001)
