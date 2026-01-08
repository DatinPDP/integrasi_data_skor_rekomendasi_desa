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
@st.cache_data(ttl=600) # Cache results for 10 minutes to prevent DB spamming
def get_options(column_name):
    try:
        # Backend expects: /unique/{year}?column={column_name}
        resp = requests.get(f"{API_URL}/unique/{YEAR}", params={"column": column_name})
        if resp.status_code == 200:
            return resp.json()
    except:
        pass
    return []

# --- FORM START ---
# Wrapping filters in a form prevents the app from reloading/querying 
# every time you type a character or select an option.
with st.form("filter_form"):
    col1, col2, col3, col4, col5 = st.columns([3, 3, 3, 3, 1], vertical_alignment="bottom")

    # Dictionary to hold our filters
    filter_params = {}

    with col1:
        prov_opts = get_options("Provinsi")
        sel_prov = st.selectbox("Provinsi", options=[""] + prov_opts, index=0)
        if sel_prov: filter_params["Provinsi"] = sel_prov

    with col2:
        kab_opts = get_options("Kabupaten/ Kota") 
        sel_kab = st.selectbox("Kabupaten/Kota", options=[""] + kab_opts, index=0)
        if sel_kab: filter_params["Kabupaten/ Kota"] = sel_kab

    with col3:
        kec_opts = get_options("Kecamatan")
        sel_kec = st.selectbox("Kecamatan", options=[""] + kec_opts, index=0)
        if sel_kec: filter_params["Kecamatan"] = sel_kec

    with col4:
        desa_val = st.text_input("Desa / Kode Wilayah", "", placeholder="Search value")
        if desa_val: filter_params["Kode Wilayah Administrasi Desa"] = desa_val

    with col5:
        # The API will ONLY be called when this button is clicked
        submitted = st.form_submit_button("Search")

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
        
        # FIX: Check if "error" key exists in the successful response
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

