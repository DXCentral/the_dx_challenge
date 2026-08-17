import streamlit as st
import datetime
import json
import streamlit.components.v1 as components
from streamlit_javascript import st_javascript

# --- MODULE IMPORTS ---
from modules.data_forge import load_all_time_master_df, get_station_databases, get_lat_lon_from_city, get_lat_lon_from_grid
from modules.bandscan_grid import render_bandscan_grid
from modules.submission_console import render_submission_console

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="THE DX CHALLENGE: SEASON 7", 
    layout="wide", 
    initial_sidebar_state="collapsed" 
)

# --- AMBER TERMINAL CSS ---
terminal_css = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;700&display=swap');

html, body, [class*="st-"] {
    background-color: #0d0a00 !important;
    font-family: 'Fira Code', monospace !important;
    color: #ffb000 !important; 
}

[data-testid="collapsedControl"] { display: none !important; }
section[data-testid="stSidebar"] { display: none !important; }

div[data-testid="stPills"] button { 
    background-color: #1a1400 !important; 
    border: 1px solid #ffb000 !important; 
    color: #ffb000 !important; 
    font-family: 'Fira Code', monospace !important; 
    font-size: 1.1rem !important;
    padding: 10px 20px !important;
}
div[data-testid="stPills"] button[data-checked="true"],
div[data-testid="stPills"] button[aria-checked="true"],
div[data-testid="stPills"] button[aria-pressed="true"] { 
    background-color: #ffb000 !important; 
    color: #0d0a00 !important; 
    font-weight: bold !important;
}
</style>
"""
st.markdown(terminal_css, unsafe_allow_html=True)

# --- BACKGROUND TASKS (LOCAL STORAGE CACHE) ---
# Silently saves the user's profile to their browser if triggered
if "profile_to_save" in st.session_state:
    js_string = json.dumps(st.session_state.profile_to_save)
    components.html(
        f"<script>window.parent.localStorage.setItem('dx_central_operator', JSON.stringify({js_string}));</script>",
        height=0, 
        width=0
    )
    del st.session_state.profile_to_save

# --- SYSTEM INITIALIZATION ---
def initialize_system():
    with st.spinner("INITIALIZING DATA FORGE..."):
        load_all_time_master_df()
        get_station_databases()
        
    if "operator_handle" not in st.session_state: st.session_state.operator_handle = "GUEST"
    if "operator_lat" not in st.session_state: st.session_state.operator_lat = 0.0
    if "operator_lon" not in st.session_state: st.session_state.operator_lon = 0.0

initialize_system()

# --- TERMINAL HEADER ---
st.markdown("<h1 style='text-align: center; color: #ffb000;'>THE DX CHALLENGE : SEASON 7</h1>", unsafe_allow_html=True)

nav_selection = st.pills(
    "MAIN MENU", 
    ["[ HOME ]", "[ BANDSCAN GRID ]", "[ SUBMIT INTERCEPT ]", "[ LEADERBOARDS ]", "[ FORENSIC RADAR ]", "[ DIRECTIVES ]"], 
    default="[ HOME ]", 
    label_visibility="collapsed",
    key="main_nav_pills"
)

st.markdown("---")

# --- THE ROUTER ---
if nav_selection == "[ HOME ]":
    st.markdown("### 🔑 OPERATOR AUTHENTICATION & LOCATION")
    
    # Attempt to load saved profile from browser cache
    js_get = "JSON.parse(localStorage.getItem('dx_central_operator'));"
    saved_data = st_javascript(js_get)
    
    if saved_data and isinstance(saved_data, dict) and not st.session_state.get('ls_loaded'):
        st.session_state.operator_handle = saved_data.get("name", "")
        st.session_state.operator_lat = float(saved_data.get("lat", 0.0))
        st.session_state.operator_lon = float(saved_data.get("lon", 0.0))
        st.session_state.ls_loaded = True
        
    if st.session_state.operator_handle != "GUEST" and st.session_state.operator_lat != 0.0:
        st.success(f"✅ SECURE DATALINK ESTABLISHED FOR CACHED OPERATOR: {st.session_state.operator_handle}")
    
    st.write("You must set your Home QTH coordinates to calculate intercept distances. Use the tools below to auto-locate.")
    
    st.markdown("#### 1. CALIBRATE LOCATION")
    cal_mode = st.radio("Calibration Method", ["City/State Search", "Maidenhead Grid", "Manual Entry"], horizontal=True, label_visibility="collapsed")
    
    if cal_mode == "City/State Search":
        c_search, c_btn = st.columns([3, 1])
        search_query = c_search.text_input("Enter City & State (e.g., 'Mandeville, LA')")
        if c_btn.button("🔍 SEARCH LOCATION", use_container_width=True):
            lat, lon = get_lat_lon_from_city(search_query)
            if lat and lon:
                st.session_state.operator_lat = lat
                st.session_state.operator_lon = lon
                st.success(f"Target Acquired: {lat:.4f}, {lon:.4f}")
            else:
                st.error("Location not found.")
                
    elif cal_mode == "Maidenhead Grid":
        c_grid, c_btn = st.columns([3, 1])
        grid_query = c_grid.text_input("Enter 4 or 6 char Grid (e.g., 'EM40')")
        if c_btn.button("🌐 CONVERT GRID", use_container_width=True):
            lat, lon = get_lat_lon_from_grid(grid_query)
            if lat and lon:
                st.session_state.operator_lat = lat
                st.session_state.operator_lon = lon
                st.success(f"Grid Converted: {lat:.4f}, {lon:.4f}")
            else:
                st.error("Invalid Grid Format.")

    st.markdown("#### 2. LOCK PROFILE")
    col1, col2, col3 = st.columns(3)
    with col1:
        op_handle = st.text_input("Callsign / Handle", value=st.session_state.operator_handle)
    with col2:
        op_lat = st.number_input("Home Latitude", value=st.session_state.operator_lat, format="%.4f")
    with col3:
        op_lon = st.number_input("Home Longitude", value=st.session_state.operator_lon, format="%.4f")
    
    c_lock, c_purge = st.columns(2)
    
    if c_lock.button("🔐 LOCK IN PROFILE & SAVE", use_container_width=True):
        st.session_state.operator_handle = op_handle.strip().upper()
        st.session_state.operator_lat = op_lat
        st.session_state.operator_lon = op_lon
        
        # Trigger the browser cache save
        st.session_state.profile_to_save = {
            "name": st.session_state.operator_handle,
            "lat": st.session_state.operator_lat,
            "lon": st.session_state.operator_lon
        }
        st.success("PROFILE LOCKED. YOU MAY PROCEED TO THE BANDSCAN GRID.")
        st.rerun()
        
    if c_purge.button("🚨 PURGE LOCAL CACHE", use_container_width=True):
        components.html("<script>window.parent.localStorage.removeItem('dx_central_operator');</script>", height=0, width=0)
        st.session_state.clear()
        st.cache_data.clear()
        st.rerun()
    
elif nav_selection == "[ BANDSCAN GRID ]":
    if st.session_state.operator_lat == 0.0 or st.session_state.operator_lon == 0.0:
        st.warning("⚠️ SYSTEM ALERT: You must set your Home Latitude and Longitude on the [ HOME ] tab before scanning.")
    else:
        render_bandscan_grid(
            user_lat=st.session_state.operator_lat, 
            user_lon=st.session_state.operator_lon,
            user_handle=st.session_state.operator_handle
        )
    
elif nav_selection == "[ SUBMIT INTERCEPT ]":
    if st.session_state.operator_lat == 0.0 or st.session_state.operator_lon == 0.0:
        st.warning("⚠️ SYSTEM ALERT: You must set your Home Latitude and Longitude on the [ HOME ] tab before submitting logs.")
    else:
        render_submission_console(
            user_lat=st.session_state.operator_lat,
            user_lon=st.session_state.operator_lon,
            user_handle=st.session_state.operator_handle
        )
    
elif nav_selection == "[ LEADERBOARDS ]":
    st.write("Leaderboards Under Construction...")
    
elif nav_selection == "[ FORENSIC RADAR ]":
    st.write("Radar Under Construction...")
    
elif nav_selection == "[ DIRECTIVES ]":
    st.write("Rules Under Construction...")
