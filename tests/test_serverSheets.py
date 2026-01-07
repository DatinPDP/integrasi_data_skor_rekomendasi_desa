import streamlit as st
import pandas as pd
import requests

# CONFIGURATION
API_URL = "http://localhost:8000"
YEAR = "2025"

# Page Layout
st.set_page_config(page_title="Desa Data Manager", layout="wide", page_icon="📊")

st.title(f"📊 Dashboard Data Desa {YEAR}")
st.markdown("Database management system with version control logic.")

# ==========================================
# SIDEBAR
# ==========================================
with st.sidebar:
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

    # --- 3. DOWNLOAD SECTION  ---
    st.header("📥 Export Data")
    
    # We use a button to trigger the API call to fetch the file
    if st.button("📄 Generate Excel Report"):
        with st.spinner("Generating Excel file..."):
            try:
                # We pass the same 'translate' param to the download endpoint
                dl_params = {"translate": translate_on}
                dl_response = requests.get(f"{API_URL}/download/{YEAR}", params=dl_params)
                
                if dl_response.status_code == 200:
                    # Create a download button for the binary content
                    st.download_button(
                        label="⬇️ Click to Download",
                        data=dl_response.content,
                        file_name=f"Laporan_Desa_{YEAR}_{'Translated' if translate_on else 'Raw'}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        type="primary"
                    )
                else:
                    st.error("Could not generate file. Is the database empty?")
            except Exception as e:
                st.error(f"Error downloading: {e}")

    st.markdown("---")
    st.caption(f"Connected to: {API_URL}")


# ==========================================
# MAIN AREA: DATA VIEWER
# ==========================================

# Filter Section
st.header("🔍 Data Browser")

col1, col2, col3 = st.columns([1, 2, 1])

with col1:
    filter_col = st.selectbox(
        "Filter By Column:",
        ["Provinsi", "Kabupaten/ Kota", "Kecamatan", "Desa", "Kode Wilayah Administrasi Desa"],
        index=0
    )

with col2:
    filter_val = st.text_input(f"Search value in '{filter_col}'...", "")

with col3:
    st.write("##") # Spacer
    refresh_btn = st.button("🔄 Refresh Data")

# Fetch Data Logic
try:
    # Build Query Params
    params = {
        "limit": 500,
        "translate": translate_on
    }

    if filter_val:
        params["filter_col"] = filter_col
        params["filter_val"] = filter_val

    # Call API
    response = requests.get(f"{API_URL}/query/{YEAR}", params=params)

    if response.status_code == 200:
        data = response.json()
        
        if data and len(next(iter(data.values()))) > 0:
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
    else:
        st.error(f"Server Error ({response.status_code}): {response.text}")

except requests.exceptions.ConnectionError:
    st.error("🚨 Cannot connect to Backend Server.")
    st.info(f"Please ensure `server.py` is running on {API_URL}")

