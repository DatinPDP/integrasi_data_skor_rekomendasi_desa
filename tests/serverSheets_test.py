import streamlit as st
import pandas as pd
import requests

# CONFIGURATION
API_URL = "http://localhost:8000"
YEAR = "2025"

# Page Layout
st.set_page_config(page_title="Desa Data Manager", layout="wide", page_icon="📊")

# Initialize Session State for Staging (Fixes "key error" on first load)
if "staging_data" not in st.session_state:
    st.session_state.staging_data = None

# ==========================================
# HELPER FUNCTIONS
# ==========================================
@st.cache_data(ttl=60) # Cache versions briefly
def get_versions():
    try:
        # Returns [{"ts": "...", "label": "..."}, ...]
        resp = requests.get(f"{API_URL}/history/versions/{YEAR}")
        if resp.status_code == 200:
            return resp.json()
    except:
        pass
    return []

@st.cache_data(ttl=3600) # Cache hierarchy tree for 1 hour
def get_hierarchy():
    try:
        resp = requests.get(f"{API_URL}/hierarchy/{YEAR}")
        if resp.status_code == 200:
            return resp.json()
    except:
        pass
    return {}

# ==========================================
# SIDEBAR
# ==========================================
with st.sidebar:
    st.caption(f"Connected to: {API_URL}")
    st.markdown("---")

    # --- 1. UPLOAD SECTION (STAGING WORKFLOW) ---
    with st.expander("📤 Upload & Update", expanded=True):
        uploaded_file = st.file_uploader("Choose .xlsb file", type=["xlsb"])

        # A. ANALYZE PHASE
        if uploaded_file:
            if st.button("1️⃣ Analyze File", type="primary"):
                with st.spinner("Analyzing Diff..."):
                    try:
                        # Reset pointer
                        files = {"file": (uploaded_file.name, uploaded_file, "application/octet-stream")}
                        uploaded_file.seek(0)
                        
                        # Call Stage Endpoint
                        res = requests.post(f"{API_URL}/stage/{YEAR}", files=files)
                        
                        if res.status_code == 200:
                            st.session_state.staging_data = res.json()
                            st.success("Analysis Complete!")
                        else:
                            st.error(f"Error: {res.text}")
                    except Exception as e:
                        st.error(f"Connection Error: {e}")

        # B. CONFIRM PHASE
        if st.session_state.staging_data:
            data = st.session_state.staging_data
            st.info(f"📄 File: {data['filename']}")
            
            # Diff Metrics
            d = data['diff']
            c1, c2, c3 = st.columns(3)
            c1.metric("➕ Add", d['added'])
            c2.metric("✏️ Edit", d['changed'])
            c3.metric("❌ Del", d['removed'])
            
            if st.button("2️⃣ Confirm Update", type="primary"):
                with st.spinner("Committing changes..."):
                    try:
                        params = {
                            "staging_id": data['staging_id'], 
                            "filename": data['filename']
                        }
                        # Call Commit Endpoint
                        res = requests.post(f"{API_URL}/commit/{YEAR}", params=params)
                        
                        if res.status_code == 200:
                            st.success("✅ Database Updated!")
                            st.session_state.staging_data = None # Reset Staging
                            st.cache_data.clear() # Clear Cache
                            st.rerun()
                        else:
                            st.error(f"Commit Failed: {res.text}")
                    except Exception as e:
                        st.error(f"Error: {e}")

    # --- 2. HISTORY / VERSION CONTROL ---
    st.markdown("### ⏳ History")
    versions = get_versions()
    # Create a mapping for the dropdown
    ver_map = {v["ts"]: v["label"] for v in versions}
    
    selected_version_ts = st.selectbox(
        "Select Data Snapshot", 
        options=[""] + list(ver_map.keys()), 
        format_func=lambda x: "🟢 Live (HEAD)" if x == "" else f"📄 {ver_map[x]}"
    )
    
    if selected_version_ts:
        st.info(f"Viewing data as of: {selected_version_ts}")

    st.markdown("---")

    # --- 3. SETTINGS ---
    st.header("⚙️ Settings")
    translate_on = st.toggle("📖 Translate Scores", value=False)
    if translate_on:
        st.caption("✅ Showing recommendations.")
    else:
        st.caption("ℹ️ Showing raw scores.")

    st.markdown("---")

# ==========================================
# MAIN AREA: FILTERS
# ==========================================
# Load Hierarchy (One time fetch)
location_tree = get_hierarchy()

# Container for all filters
with st.container(border=True):
    st.subheader("🔍 Filters")

    # ROW 1: Hierarchy Dropdowns
    col1, col2, col3 = st.columns(3)
    filter_params = {}

    with col1:
        prov_options = sorted(list(location_tree.keys()))
        sel_prov = st.selectbox("Provinsi", options=[""] + prov_options, index=0)
        if sel_prov: filter_params["Provinsi"] = sel_prov

    with col2:
        kab_options = sorted(list(location_tree[sel_prov].keys())) if sel_prov else []
        sel_kab = st.selectbox("Kabupaten/Kota", options=[""] + kab_options, index=0)
        if sel_kab: filter_params["Kabupaten/ Kota"] = sel_kab

    with col3:
        kec_options = sorted(location_tree[sel_prov][sel_kab]) if (sel_prov and sel_kab) else []
        sel_kec = st.selectbox("Kecamatan", options=[""] + kec_options, index=0)
        if sel_kec: filter_params["Kecamatan"] = sel_kec

    # ROW 2: ID List & Name Search
    col4, col5 = st.columns([3, 1])
    
    with col4:
        # ID LIST FILTER
        id_input = st.text_area(
            "Paste IDs (comma or newline separated)", 
            placeholder="1001234001\n1001234002",
            height=100,
            help="Paste a list of Kode Wilayah to filter specifically for those villages."
        )
        if id_input.strip():
            # Clean string for the API (replace newlines with commas)
            clean_ids = ",".join([x.strip() for x in id_input.replace("\n", ",").split(",") if x.strip()])
            filter_params["ids"] = clean_ids

    with col5:
        # Standard Name Search
        desa_val = st.text_input("Search Name/Code", placeholder="Nama Desa...")
        if desa_val: filter_params["Kode Wilayah Administrasi Desa"] = desa_val
        
        st.write("") # Spacer
        search_clicked = st.button("🔍 Search Data", type="primary", use_container_width=True)

# ==========================================
# DOWNLOAD SECTION
# ==========================================
with st.sidebar:
    if st.button("📥 Export Filtered Excel"):
        with st.spinner("Generating Excel file..."):
            try:
                # Base Params
                dl_params = {"translate": translate_on}
                dl_params.update(filter_params)
                if selected_version_ts:
                    dl_params["version"] = selected_version_ts
                
                dl_response = requests.get(f"{API_URL}/download/{YEAR}", params=dl_params)
                
                if dl_response.status_code == 200:
                    st.download_button(
                        label="⬇️ Click to Download",
                        data=dl_response.content,
                        file_name=f"Laporan_{YEAR}_{'Translated' if translate_on else 'Raw'}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        type="primary"
                    )
                else:
                    st.error("Download failed.")
            except Exception as e:
                st.error(f"Error: {e}")

# ==========================================
# DATA FETCHING & DISPLAY
# ==========================================
# Run query if search clicked or always (default view)
if search_clicked or True: 
    try:
        # 1. Build Params
        api_params = {
            "limit": 50000,
            "translate": translate_on
        }
        api_params.update(filter_params)
        
        if selected_version_ts:
            api_params["version"] = selected_version_ts

        # 2. Call API
        response = requests.get(f"{API_URL}/query/{YEAR}", params=api_params)

        if response.status_code == 200:
            data = response.json()
            df = pd.DataFrame()
            
            # --- HANDLE DATA FORMATS ---
            # Case 1: Error Message
            if isinstance(data, dict) and "error" in data:
                st.warning(data["error"])
            
            # Case 2: List of Rows (New Server)
            elif isinstance(data, list):
                if len(data) > 0: df = pd.DataFrame(data)
            
            # Case 3: Dict of Cols (Legacy)
            elif isinstance(data, dict):
                if "error" in data:
                    st.warning(data["error"])
                elif len(next(iter(data.values()))) > 0:
                     df = pd.DataFrame(data)

            # Display Data
            if not df.empty:
                m1, m2, m3 = st.columns(3)
                m1.metric("Total Rows", f"{len(df):,}")
                
                # Intelligent Date Finder
                last_up = "N/A"
                if 'valid_from' in df.columns: last_up = str(df['valid_from'].iloc[0])
                elif 'last_updated' in df.columns: last_up = str(df['last_updated'].iloc[0])
                
                m3.metric("Mode", "Snapshot" if selected_version_ts else "Live")

                # Display only first 1000 rows to prevent lag
                if len(df) > 1000:
                    st.caption(f"ℹ️ Showing first 1,000 of {len(df):,} rows.")
                    display_df = df.head(1000)
                else:
                    display_df = df

                st.dataframe(
                    display_df,
                    use_container_width=True,
                    height=600,
                    hide_index=True
                )
            elif not (isinstance(data, dict) and "error" in data):
                st.warning("No data found matching your criteria.")
        
        elif response.status_code == 404:
            st.info("Database is empty. Please upload an Excel file.")
        else:
            st.error(f"Server Error ({response.status_code}): {response.text}")

    except requests.exceptions.ConnectionError:
        st.error(f"🚨 Cannot connect to Backend Server at {API_URL}")
