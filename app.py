import streamlit as st
import datetime

# Modules
from modules.terminal_home import render_terminal_home
# (Other module imports will go here: submit_log, dashboards, etc.)

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

# --- TERMINAL HEADER ---
st.markdown("<h1 style='text-align: center; color: #ffb000;'>THE DX CHALLENGE : SEASON 7</h1>", unsafe_allow_html=True)

# --- PERSISTENT TOP NAVIGATION ---
# This entirely replaces the sidebar menu. 
nav_selection = st.pills(
    "MAIN MENU", 
    ["[ HOME ]", "[ SUBMIT INTERCEPT ]", "[ LEADERBOARDS ]", "[ FORENSIC RADAR ]", "[ DIRECTIVES ]"], 
    default="[ HOME ]", 
    label_visibility="collapsed",
    key="main_nav_pills"
)

st.markdown("---") # Visual separator line

# --- THE ROUTER ---
if nav_selection == "[ HOME ]":
    render_terminal_home()
    
elif nav_selection == "[ SUBMIT INTERCEPT ]":
    st.write("Submission Form Under Construction...")
    # render_unified_submission_form()
    
elif nav_selection == "[ LEADERBOARDS ]":
    st.write("Leaderboards Under Construction...")
    # render_dashboards()
    
elif nav_selection == "[ FORENSIC RADAR ]":
    st.write("Radar Under Construction...")
    # render_maps_and_radar()
    
elif nav_selection == "[ DIRECTIVES ]":
    st.write("Rules Under Construction...")
    # render_rules()
