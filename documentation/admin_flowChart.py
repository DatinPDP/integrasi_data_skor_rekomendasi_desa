from graphviz import Digraph

def flowchart():
    # Initialize graph with Top-Bottom direction, orthogonal lines, and improved spacing
    dot = Digraph('Admin_Architecture_Flow', format='svg')

    # nodesep = horizontal spacing, ranksep = vertical spacing
    dot.attr(rankdir='TB', splines='ortho', nodesep='1', ranksep='1', compound='true', forcelabels='true')

    # Global node styles with padding (margin) for readability
    dot.attr('node', shape='box', style='rounded,filled', fontname='Helvetica', fontsize='11', margin='0.3,0.15')
    dot.attr('edge', fontname='Helvetica', fontsize='9', color='#555555')

    # --- ENTRY POINTS ---
    dot.node('User', 'User Request\n(Browser)', shape='oval', fillcolor='#D1C4E9')

    # --- CLUSTER: FRONTEND & ROUTER (Port 8001) ---
    with dot.subgraph(name='cluster_frontend') as fe:
        fe.attr(style='filled', fillcolor='#E3F2FD', color='#90CAF9', label='FRONTEND & SSR ROUTER (Port 8001)', fontname='Helvetica-Bold', margin='20')

        fe.node('Router', 'Router (router.py)\nIntercepts all traffic', fillcolor='#BBDEFB')
        fe.node('Route_404', '404 Handler\nServe templates/404.html', fillcolor='#FFCDD2')
        fe.node('Route_CheckJWT', 'Verify JWT Session Cookie\nGet Role (Admin/User)', fillcolor='#BBDEFB')

        fe.node('Login_UI', 'Login Page (login.html)\nSubmit Username/Password', fillcolor='#90CAF9')

        #ADMIN_UI taller & wider to handle many incoming arrows
        fe.node('Admin_UI', 'Admin Dashboard (admin.html)\nAlpine.js + AG Grid Init', 
                fillcolor='#90CAF9', height='4')

        # UI Action Nodes (Upload Flow)
        fe.node('UI_Upload_Start', 'Select .xlsx & Compute SparkMD5', fillcolor='#FFF9C4')
        fe.node('UI_Upload_Chunk', 'Chunk Upload Loop\nSend 2MB pieces', fillcolor='#FFF9C4')
        fe.node('UI_Upload_Preview', 'Preview Excel (First 25 Rows)\nSelect Header & Data Start', fillcolor='#FFF9C4')
        fe.node('UI_Upload_Mapping', 'Verify Column Mapping\n(Review Missing Headers Warning)', fillcolor='#FFF9C4')
        fe.node('UI_Upload_Review', 'Review CDC Diff\n(Add/Mod/Del Counts)', fillcolor='#FFF9C4')

        # UI Action Nodes (Dashboard & General)
        fe.node('UI_Filters', 'Update Sidebar Filters & Year\n(Triggers Refresh Loop)', fillcolor='#C8E6C9', height='2.5')

    # --- CLUSTER: BACKEND (Port 8000) ---
    with dot.subgraph(name='cluster_backend') as be:
        be.attr(style='filled', fillcolor='#F5F5F5', color='#BDBDBD', label='BACKEND API (server.py / middleware.py)', fontname='Helvetica-Bold', margin='20')

        # Auth
        be.node('API_Login', '/api/login\nVerify bcrypt Password', fillcolor='#E0E0E0')
        be.node('Logic_JWT', 'Generate JWT Token\nSet HttpOnly Cookie', fillcolor='#A5D6A7')

        # Upload
        be.node('API_Init', '/upload/init\nCheck Hash/Size', fillcolor='#E0E0E0')
        be.node('API_Chunk', '/upload/chunk\nAppend Bytes & Verify Hash', fillcolor='#E0E0E0')
        be.node('API_Finalize', '/upload/finalize\nVerify Total MD5 Hash', fillcolor='#E0E0E0')
        be.node('API_Analyze', '/upload/analyze-headers\nFuzzy Match & Check Missing Headers', fillcolor='#E0E0E0')
        be.node('API_Process', '/upload/process-mapped\nPolars ETL, Drop Nulls, Cast Types', fillcolor='#E0E0E0')
        be.node('API_Commit', '/commit\nExecute SQL Transaction', fillcolor='#E0E0E0')

        # Dashboard Data
        be.node('API_Query', '/query\nDuckDB -> Polars -> JSON Stream', fillcolor='#E0E0E0')
        be.node('API_Rekomendasi', '/dashboard/calculate\nAggregate Scores & Narrative (HTML)', fillcolor='#E0E0E0')
        be.node('API_IKU', '/dashboard/iku\nGroup Hierarchy & Heatmap (HTML)', fillcolor='#E0E0E0')

        # Tools
        be.node('API_History', '/history/details\nCompare valid_from / valid_to', fillcolor='#E0E0E0')
        be.node('API_Delete', '/delete\nSoft Delete target IDs', fillcolor='#E0E0E0')
        be.node('API_Download', '/download/excel\nDynamic Workbook or Precompiled', fillcolor='#E0E0E0')

    # --- CLUSTER: STORAGE & CONFIG (TOP-TO-BOTTOM) ---
    with dot.subgraph(name='cluster_storage') as db:
        db.attr(style='filled', fillcolor='#FFF3E0', color='#FFCC80', label='STORAGE & CONFIG', fontname='Helvetica-Bold', margin='20')

        db.node('DB_DuckDB', 'DuckDB (dbs/)\nSCD Type 2 master_data', shape='cylinder', fillcolor='#FFE0B2', height='2.5')
        db.node('Cfg_Users', 'auth_users.json', shape='folder', fillcolor='#FFE0B2')
        db.node('Cfg_Logic', 'headers.json, rekomendasi.json\nTable Structures etc.', shape='folder', fillcolor='#FFE0B2', height='2')
        db.node('Export_Dir', 'exports/ directory\nPrecompiled Master XLSX', shape='folder', fillcolor='#FFE0B2')

        # Force vertical top-to-bottom layout (removes left-to-right clutter)
        db.edge('DB_DuckDB', 'Cfg_Users', style='invis', weight='100')
        db.edge('Cfg_Users', 'Cfg_Logic', style='invis', weight='100')
        db.edge('Cfg_Logic', 'Export_Dir', style='invis', weight='100')

    # ==========================================
    # ROUTING & AUTHENTICATION
    # ==========================================
    dot.edge('User', 'Router')
    dot.edge('Router', 'Route_404', xlabel='Invalid URL')
    dot.edge('Router', 'Route_CheckJWT', xlabel='Valid Endpoint')

    dot.edge('Route_CheckJWT', 'Login_UI', xlabel='Missing/Invalid Token')
    dot.edge('Route_CheckJWT', 'Admin_UI', xlabel='Valid Admin Token')

    dot.edge('Login_UI', 'API_Login', xlabel='POST Credentials')

    # DB Auth Loop
    dot.edge('API_Login', 'Cfg_Users', xlabel='Lookup Hash')
    dot.edge('Cfg_Users', 'API_Login', xlabel='[RETURN] User Data', color='#0f766e', fontcolor='#0f766e', constraint='false')

    dot.edge('API_Login', 'Login_UI', xlabel='[LOOP] Invalid Credentials', color='red', fontcolor='red', constraint='false')
    dot.edge('API_Login', 'Logic_JWT', xlabel='Valid Password')
    dot.edge('Logic_JWT', 'Admin_UI', xlabel='Redirect to Dashboard', constraint='false')

    # ==========================================
    # UPLOAD & ETL PROCESS
    # ==========================================
    dot.edge('Admin_UI', 'UI_Upload_Start', xlabel='Click Upload')
    dot.edge('UI_Upload_Start', 'API_Init', xlabel='Send MD5/Size')

    # Chunking Loop
    dot.edge('API_Init', 'UI_Upload_Chunk', xlabel='Requires Upload', constraint='false')
    dot.edge('UI_Upload_Chunk', 'API_Chunk', xlabel='Send 2MB Chunk')
    dot.edge('API_Chunk', 'UI_Upload_Chunk', xlabel='[LOOP] Network/Hash Error', color='red', fontcolor='red', constraint='false')
    dot.edge('API_Chunk', 'UI_Upload_Chunk', xlabel='[LOOP] Request Next Chunk', color='#0f766e', fontcolor='#0f766e', constraint='false')
    dot.edge('API_Chunk', 'API_Finalize', xlabel='All Chunks Sent')

    # Finalize & Preview
    dot.edge('API_Finalize', 'UI_Upload_Start', xlabel='[LOOP] Final MD5 Mismatch', color='red', fontcolor='red', constraint='false')
    dot.edge('API_Finalize', 'UI_Upload_Preview', xlabel='Success -> Returns temp_id', constraint='false')

    # Mapping Loop
    dot.edge('UI_Upload_Preview', 'API_Analyze', xlabel='Submit Header/Data Row Index')
    dot.edge('API_Analyze', 'Cfg_Logic', xlabel='Read headers.json')
    dot.edge('Cfg_Logic', 'API_Analyze', xlabel='[RETURN] Schema Details', color='#0f766e', fontcolor='#0f766e', constraint='false')
    dot.edge('API_Analyze', 'UI_Upload_Mapping', xlabel='Returns Mapping + Missing Headers Warning', constraint='false')

    # Processing Loop
    dot.edge('UI_Upload_Mapping', 'API_Process', xlabel='Start Processing')
    dot.edge('API_Process', 'DB_DuckDB', xlabel='Compare CDC Diff')
    dot.edge('DB_DuckDB', 'API_Process', xlabel='[RETURN] Existing Data', color='#0f766e', fontcolor='#0f766e', constraint='false')
    dot.edge('API_Process', 'UI_Upload_Preview', xlabel='[LOOP] Validation Error (e.g. Bad Status ID)', color='red', fontcolor='red', constraint='false')
    dot.edge('API_Process', 'UI_Upload_Review', xlabel='Success -> Returns Add/Mod/Del Stats', constraint='false')

    # Commit
    dot.edge('UI_Upload_Review', 'Admin_UI', xlabel='[LOOP] Admin Cancels', constraint='false')
    dot.edge('UI_Upload_Review', 'API_Commit', xlabel='Confirm Upload Database')
    dot.edge('API_Commit', 'DB_DuckDB', xlabel='SQL: Update valid_to=Now\nInsert valid_to=NULL')
    dot.edge('DB_DuckDB', 'API_Commit', xlabel='[RETURN] Transaction Success', color='#0f766e', fontcolor='#0f766e', constraint='false')
    dot.edge('API_Commit', 'UI_Filters', xlabel='Trigger Auto-Refresh', constraint='false')

    # ==========================================
    # DASHBOARD FEEDBACK LOOPS
    # ==========================================
    dot.edge('Admin_UI', 'UI_Filters', xlabel='Change View / Filter / Sort')

    # Dashboard Endpoints Triggered by Filter UI
    dot.edge('UI_Filters', 'API_Query', xlabel='Grid View Active')
    dot.edge('UI_Filters', 'API_Rekomendasi', xlabel='Rekomendasi Active')
    dot.edge('UI_Filters', 'API_IKU', xlabel='IKU Active')

    # Backend Data Fetching & Returns
    dot.edge('API_Query', 'DB_DuckDB', xlabel='Execute Query')
    dot.edge('DB_DuckDB', 'API_Query', xlabel='[RETURN] Raw Data', color='#0f766e', fontcolor='#0f766e', constraint='false')
    dot.edge('API_Rekomendasi', 'DB_DuckDB', xlabel='Execute Filter')
    dot.edge('DB_DuckDB', 'API_Rekomendasi', xlabel='[RETURN] Filtered Data', color='#0f766e', fontcolor='#0f766e', constraint='false')
    dot.edge('API_IKU', 'DB_DuckDB', xlabel='Execute Filter')
    dot.edge('DB_DuckDB', 'API_IKU', xlabel='[RETURN] Filtered Data', color='#0f766e', fontcolor='#0f766e', constraint='false')

    # Config Reading & Returns
    dot.edge('API_Rekomendasi', 'Cfg_Logic', xlabel='Read Formats/Intervensi')
    dot.edge('Cfg_Logic', 'API_Rekomendasi', xlabel='[RETURN] Logic Templates', color='#0f766e', fontcolor='#0f766e', constraint='false')
    dot.edge('API_IKU', 'Cfg_Logic', xlabel='Read IKU Hierarchy')
    dot.edge('Cfg_Logic', 'API_IKU', xlabel='[RETURN] IKU Mapping', color='#0f766e', fontcolor='#0f766e', constraint='false')

    # Loop back to UI rendering
    dot.edge('API_Query', 'Admin_UI', xlabel='[LOOP] Render JSON to AG Grid', color='blue', constraint='false')
    dot.edge('API_Rekomendasi', 'Admin_UI', xlabel='[LOOP] Render HTML Table', color='blue', constraint='false')
    dot.edge('API_IKU', 'Admin_UI', xlabel='[LOOP] Render HTML Heatmap', color='blue', constraint='false')

    # ==========================================
    # HISTORY, DELETE, DOWNLOAD LOOPS
    # ==========================================
    # History
    dot.edge('Admin_UI', 'API_History', xlabel='Expand History Sidebar')
    dot.edge('API_History', 'DB_DuckDB', xlabel='Query Target Timestamp')
    dot.edge('DB_DuckDB', 'API_History', xlabel='[RETURN] Historical Data', color='#0f766e', fontcolor='#0f766e', constraint='false')
    dot.edge('API_History', 'Admin_UI', xlabel='[LOOP] Show Diff Details', color='blue', constraint='false')

    # Delete
    dot.edge('Admin_UI', 'API_Delete', xlabel='Submit IDs')
    dot.edge('API_Delete', 'DB_DuckDB', xlabel='UPDATE valid_to=Now')
    dot.edge('DB_DuckDB', 'API_Delete', xlabel='[RETURN] Deleted Count', color='#0f766e', fontcolor='#0f766e', constraint='false')
    dot.edge('API_Delete', 'Admin_UI', xlabel='[LOOP] ID Not Found (Warning)', color='orange', fontcolor='orange', constraint='false')
    dot.edge('API_Delete', 'UI_Filters', xlabel='Success -> Trigger Auto-Refresh', constraint='false')

    # Download
    dot.edge('Admin_UI', 'API_Download', xlabel='Request Excel')
    dot.edge('API_Download', 'Export_Dir', xlabel='No Filters -> Check Static (Pre-Compiled)')
    dot.edge('Export_Dir', 'API_Download', xlabel='[RETURN] Static File (Pre-Compiled)', color='#0f766e', fontcolor='#0f766e', constraint='false')
    dot.edge('API_Download', 'DB_DuckDB', xlabel='Filters Active -> Query Dynamic Data')
    dot.edge('DB_DuckDB', 'API_Download', xlabel='[RETURN] Dynamic Data', color='#0f766e', fontcolor='#0f766e', constraint='false')
    dot.edge('API_Download', 'Admin_UI', xlabel='[LOOP] Trigger File Download', color='blue', constraint='false')

    # ==========================================
    # FORCE STORAGE CLUSTER TO RENDER BELOW BACKEND
    # ==========================================
    dot.edge('API_Commit', 'DB_DuckDB', style='invis', minlen='3', weight='100')
    dot.edge('API_IKU', 'Cfg_Logic', style='invis', minlen='3', weight='100')

    # Render configurations
    dot.render('Admin Architecture Flow Chart', cleanup=True)
    dot.save('Admin Architecture Flow Chart.dot')

if __name__ == '__main__':
    flowchart()
