import streamlit as st
import pandas as pd
import requests

# CONFIGURATION
API_URL = "http://localhost:8000"
YEAR = "2025"

# Page Layout
st.set_page_config(page_title="Desa Data Manager", layout="wide", page_icon="📊")

# ==========================================
# SIDEBAR
# ==========================================
with st.sidebar:
    st.caption(f"Connected to: {API_URL}")
    st.markdown("---")

    # --- 1. UPLOAD SECTION ---
    st.header("📤 Upload Data")
    st.info("Upload .xlsb files here to update the database.")
    
    uploaded_file = st.file_uploader("Choose an XLSB file", type=["xlsb"])
    
    if uploaded_file is not None:
        if st.button("🚀 Process & Upload", type="primary"):
            with st.spinner("Processing file... (This may take a moment)"):
                try:
                    # Prepare file for API
                    files = {"file": (uploaded_file.name, uploaded_file, "application/octet-stream")}
                    # Reset file pointer to beginning
                    uploaded_file.seek(0)
                    
                    response = requests.post(f"{API_URL}/upload/{YEAR}", files=files)
                    
                    if response.status_code == 200:
                        res_json = response.json()
                        st.success("✅ Upload Successful!")
                        st.json(res_json)
                        st.rerun() # Refresh app to show new data
                    else:
                        st.error(f"❌ Upload Failed: {response.text}")
                except Exception as e:
                    st.error(f"Connection Error: {e}")

    st.markdown("---")

    # --- 2. VIEW SETTINGS  ---
    st.header("⚙️ View Settings")
    
    # THE TRANSLATE TOGGLE
    # This sends "true" or "false" to the backend
    translate_on = st.toggle("📖 Translate Scores to Text", value=False)
    
    if translate_on:
        st.caption("✅ Data is being translated into recommendations.")
    else:
        st.caption("ℹ️ Showing raw numerical scores (1-5).")

    st.markdown("---")

# ==========================================
# MAIN AREA: DATA VIEWER
# ==========================================

# Helper to get options for dropdowns
@st.cache_data(ttl=3600) # Cache the tree for 1 hour to prevent DB spamming
def get_hierarchy():
    try:
        resp = requests.get(f"{API_URL}/hierarchy/{YEAR}")
        if resp.status_code == 200:
            return resp.json()
    except:
        pass
    return {}

# Load Hierarchy (One time fetch)
location_tree = get_hierarchy()

# --- FILTER CONTROLS ---
# searchable dropdowns for hierarchical location selection
col1, col2, col3, col4, col5 = st.columns([3, 3, 3, 3, 1], vertical_alignment="bottom")
filter_params = {}

with col1:
    # Level 1: Provinsi keys
    prov_options = sorted(list(location_tree.keys()))
    sel_prov = st.selectbox("Provinsi", options=[""] + prov_options, index=0)
    if sel_prov: filter_params["Provinsi"] = sel_prov

with col2:
    # Level 2: Get keys of the selected Provinsi
    kab_options = []
    if sel_prov and sel_prov in location_tree:
        kab_options = sorted(list(location_tree[sel_prov].keys()))
    
    sel_kab = st.selectbox("Kabupaten/Kota", options=[""] + kab_options, index=0)
    if sel_kab: filter_params["Kabupaten/ Kota"] = sel_kab

with col3:
    # Level 3: Get list from selected Kabupaten
    kec_options = []
    if sel_prov and sel_kab and sel_kab in location_tree.get(sel_prov, {}):
        kec_options = sorted(location_tree[sel_prov][sel_kab])
        
    sel_kec = st.selectbox("Kecamatan", options=[""] + kec_options, index=0)
    if sel_kec: filter_params["Kecamatan"] = sel_kec

with col4:
    desa_val = st.text_input("Desa / Kode Wilayah", "", placeholder="Search value")
    if desa_val: filter_params["Kode Wilayah Administrasi Desa"] = desa_val

with col5:
    # This button triggers the ACTUAL DB Query
    if st.button("Search"):
        st.rerun()

# --- DOWNLOAD BUTTON LOGIC ---
if st.sidebar.button("📄 Generate Filtered Report"):
    with st.sidebar:
        with st.spinner("Generating Excel file..."):
            try:
                # Base Params
                dl_params = {"translate": translate_on}
                # Add Active Filters
                dl_params.update(filter_params) 
                
                dl_response = requests.get(f"{API_URL}/download/{YEAR}", params=dl_params)
                
                if dl_response.status_code == 200:
                    st.download_button(
                        label="⬇️ Click to Download",
                        data=dl_response.content,
                        file_name=f"Laporan_Desa_{YEAR}_{'Translated' if translate_on else 'Raw'}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        type="primary"
                    )
                else:
                    st.error("Download failed.")
            except Exception as e:
                st.error(f"Error: {e}")

# Fetch Data Logic
try:
    # Build Query Params
    api_params = {
        "limit": 500,
        "translate": translate_on
    }
    api_params.update(filter_params) # Merge filter selections

    # Call API
    response = requests.get(f"{API_URL}/query/{YEAR}", params=api_params)

    if response.status_code == 200:
        data = response.json()
        
        # Check if "error" key exists in the successful response
        if "error" in data:
            st.warning(data["error"])
            
        elif data and len(next(iter(data.values()))) > 0:
            # Convert JSON dict to Pandas DataFrame for display
            df = pd.DataFrame(data)
            
            # --- DISPLAY METRICS ---
            m1, m2 = st.columns(2)
            m1.metric("Rows Displayed", len(df))
            m2.metric("Latest Update", df['last_updated'].iloc[0] if 'last_updated' in df.columns else "N/A")

            # --- INTERACTIVE TABLE ---
            # st.dataframe provides sorting, resizing, and scrolling automatically
            st.dataframe(
                df,
                use_container_width=True,
                height=600,
                hide_index=True,
                column_config={
                    "last_updated": st.column_config.DatetimeColumn("Last Updated", format="D MMM YYYY, HH:mm:ss"),
                }
            )
        else:
            st.warning("No data found matching your criteria.")
    
    elif response.status_code == 404:
        st.info("Database is empty. Please upload an Excel file.")
        
    else:
        st.error(f"Server Error ({response.status_code}): {response.text}")

except requests.exceptions.ConnectionError:
    st.error("🚨 Cannot connect to Backend Server.")
    st.info(f"Please ensure `server.py` is running on {API_URL}")

