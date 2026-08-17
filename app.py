import streamlit as st
import datetime

# --- MODULE IMPORTS ---
# from modules.terminal_home import render_terminal_home
from modules.data_forge import load_all_time_master_df, get_station_databases
from modules.bandscan_grid import render_bandscan_grid
from modules.submission_console import render_submission_console

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="THE DX CHALLENGE: SEASON 7", 
    layout="wide", 
    initial_sidebar_state="collapsed" # We collapse it by default since we aren't using it
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

/* Hide the default Streamlit sidebar toggle entirely to prevent accidental clicks */
[data-testid="collapsedControl"] { display: none !important; }
section[data-testid="stSidebar"] { display: none !important; }

/* Top Navigation Pill Styling */
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

# --- SYSTEM INITIALIZATION ---
def initialize_system():
    """Warms up the data forge and establishes the terminal state."""
    with st.spinner("INITIALIZING DATA FORGE..."):
        load_all_time_master_df()
        get_station_databases()
        
    if "operator_handle" not in st.session_state:
        st.session_state.operator_handle = "GUEST"
    if "operator_lat" not in st.session_state:
        st.session_state.operator_lat = 0.0
    if "operator_lon" not in st.session_state:
        st.session_state.operator_lon = 0.0

initialize_system()

# --- TERMINAL HEADER ---
st.markdown("<h1 style='text-align: center; color: #ffb000;'>THE DX CHALLENGE : SEASON 7</h1>", unsafe_allow_html=True)

# --- PERSISTENT TOP NAVIGATION ---
# This entirely replaces the sidebar menu. 
nav_selection = st.pills(
    "MAIN MENU", 
    ["[ HOME ]", "[ BANDSCAN GRID ]", "[ SUBMIT INTERCEPT ]", "[ LEADERBOARDS ]", "[ FORENSIC RADAR ]", "[ DIRECTIVES ]"], 
    default="[ HOME ]", 
    label_visibility="collapsed",
    key="main_nav_pills"
)

st.markdown("---") # Visual separator line

# --- THE ROUTER ---
if nav_selection == "[ HOME ]":
    # Operator Login Block (Moved from sidebar)
    st.markdown("### 🔑 OPERATOR LOGIN & PROFILE")
    col1, col2, col3 = st.columns(3)
    with col1:
        op_handle = st.text_input("Callsign / Handle", value=st.session_state.operator_handle)
    with col2:
        op_lat = st.number_input("Home Latitude", value=st.session_state.operator_lat, format="%.4f")
    with col3:
        op_lon = st.number_input("Home Longitude", value=st.session_state.operator_lon, format="%.4f")
    
    if st.button("SET PROFILE"):
        st.session_state.operator_handle = op_handle.strip().upper()
        st.session_state.operator_lat = op_lat
        st.session_state.operator_lon = op_lon
        st.success("PROFILE LOCKED")
        st.rerun()
        
    st.markdown("---")
    # render_terminal_home()
    st.write("Home Dashboard Loading...")
    
elif nav_selection == "[ BANDSCAN GRID ]":
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
    # render_dashboards()
    
elif nav_selection == "[ FORENSIC RADAR ]":
    st.write("Radar Under Construction...")
    # render_maps_and_radar()
    
elif nav_selection == "[ DIRECTIVES ]":
    st.write("Rules Under Construction...")
    # render_rules()
