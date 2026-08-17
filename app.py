import streamlit as st
import datetime
import json
import streamlit.components.v1 as components
from streamlit_javascript import st_javascript
from geopy.geocoders import Nominatim

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

# --- TERMINAL CSS (WITH TACTICAL RED PILLS) ---
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

/* GLOBAL PILL STYLING */
div[data-testid="stPills"] button { 
    background-color: #1a1400 !important; 
    border: 1px solid #ffb000 !important; 
    color: #ffb000 !important; 
    font-family: 'Fira Code', monospace !important; 
    font-size: 1.1rem !important;
    padding: 10px 20px !important;
}

/* RED RING ACTIVE PILL OVERRIDE */
div[data-testid="stPills"] button[data-checked="true"],
div[data-testid="stPills"] button[aria-checked="true"],
div[data-testid="stPills"] button[aria-pressed="true"] { 
    background-color: #3a0000 !important; 
    border: 2px solid #ff0000 !important; 
    color: #ffffff !important; 
    font-weight: bold !important;
    box-shadow: 0px 0px 10px rgba(255,0,0,0.8) !important; 
}
</style>
"""
st.markdown(terminal_css, unsafe_allow_html=True)

# --- REVERSE GEOCODER HELPER ---
def do_reverse_geocode(lat, lon):
    """Automatically looks up the City, State, and Country based on Coordinates."""
    try:
        geolocator = Nominatim(user_agent="dx_central_s7_rev", timeout=5)
        location = geolocator.reverse(f"{lat}, {lon}", language='en')
        if location:
            addr = location.raw.get('address', {})
            found_city = ""
            for tag in ['city', 'town', 'village', 'hamlet']:
                if tag in addr: 
                    found_city = addr[tag]
                    break
            state = addr.get('state', addr.get('province', ''))
            country = addr.get('country', 'United States')
            return found_city, state, country
    except Exception: 
        pass
    return "", "", "United States"

# --- BACKGROUND TASKS (LOCAL STORAGE CACHE) ---
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
    with st.spinner("Loading Databases..."):
        load_all_time_master_df()
        get_station_databases()
        
    if "operator_handle" not in st.session_state: st.session_state.operator_handle = ""
    if "operator_city" not in st.session_state: st.session_state.operator_city = ""
    if "operator_state" not in st.session_state: st.session_state.operator_state = ""
    if "operator_country" not in st.session_state: st.session_state.operator_country = "United States"
    if "operator_lat" not in st.session_state: st.session_state.operator_lat = 0.0
    if "operator_lon" not in st.session_state: st.session_state.operator_lon = 0.0

initialize_system()

# --- TERMINAL HEADER ---
st.markdown("<h1 style='text-align: center; color: #ffb000;'>THE DX CHALLENGE : SEASON 7</h1>", unsafe_allow_html=True)

nav_selection = st.pills(
    "MAIN MENU", 
    ["[ HOME ]", "[ BANDSCAN GRID ]", "[ SUBMIT RECEPTION ]", "[ LEADERBOARDS ]", "[ MAPS & RADAR ]", "[ RULES ]"], 
    default="[ HOME ]", 
    selection_mode="single",
    label_visibility="collapsed",
    key="main_nav_pills"
)

st.markdown("---")

# --- THE ROUTER ---
if nav_selection == "[ HOME ]":
    st.markdown("### 👤 MY PROFILE")
    
    # Attempt to load saved profile from browser cache
    js_get = "JSON.parse(localStorage.getItem('dx_central_operator'));"
    saved_data = st_javascript(js_get)
    
    if saved_data and isinstance(saved_data, dict) and not st.session_state.get('ls_loaded'):
        st.session_state.operator_handle = saved_data.get("name", "")
        st.session_state.operator_city = saved_data.get("city", "")
        st.session_state.operator_state = saved_data.get("state", "")
        st.session_state.operator_country = saved_data.get("country", "United States")
        st.session_state.operator_lat = float(saved_data.get("lat", 0.0))
        st.session_state.operator_lon = float(saved_data.get("lon", 0.0))
        st.session_state.ls_loaded = True
        st.rerun() # Refresh to populate the fields smoothly
        
    st.write("You must set your Home location to calculate reception distances automatically. Use the tools below to auto-locate, then verify your details.")
    
    st.markdown("#### 1. SET YOUR LOCATION")
    cal_mode = st.pills("Search Method", ["City/State Search", "Maidenhead Grid", "Manual Entry"], default="City/State Search", selection_mode="single", label_visibility="collapsed")
    
    if cal_mode == "City/State Search":
        c_search, c_btn = st.columns([3, 1])
        search_query = c_search.text_input("Enter City & State (e.g., 'Mandeville, LA')")
        if c_btn.button("🔍 Search Location", use_container_width=True):
            lat, lon = get_lat_lon_from_city(search_query)
            if lat and lon:
                city, state, country = do_reverse_geocode(lat, lon)
                st.session_state.operator_lat = lat
                st.session_state.operator_lon = lon
                st.session_state.operator_city = city
                st.session_state.operator_state = state
                st.session_state.operator_country = country
                st.success(f"Location found: {city}, {state}, {country} ({lat:.4f}, {lon:.4f})")
            else:
                st.error("Location not found. Please try again or use Manual Entry.")
                
    elif cal_mode == "Maidenhead Grid":
        c_grid, c_btn = st.columns([3, 1])
        grid_query = c_grid.text_input("Enter 4 or 6 char Grid (e.g., 'EM40')")
        if c_btn.button("🌐 Convert Grid", use_container_width=True):
            lat, lon = get_lat_lon_from_grid(grid_query)
            if lat and lon:
                city, state, country = do_reverse_geocode(lat, lon)
                st.session_state.operator_lat = lat
                st.session_state.operator_lon = lon
                st.session_state.operator_city = city
                st.session_state.operator_state = state
                st.session_state.operator_country = country
                st.success(f"Location found: {city}, {state}, {country} ({lat:.4f}, {lon:.4f})")
            else:
                st.error("Invalid Grid Format.")

    st.markdown("#### 2. YOUR DETAILS")
    c1, c2, c3 = st.columns(3)
    op_handle = c1.text_input("Name / How you want to be identified", value=st.session_state.operator_handle)
    op_city = c2.text_input("City", value=st.session_state.operator_city)
    op_state = c3.text_input("State / Province", value=st.session_state.operator_state)
    
    c4, c5, c6 = st.columns(3)
    op_country = c4.text_input("Country", value=st.session_state.operator_country)
    op_lat = c5.number_input("Latitude", value=st.session_state.operator_lat, format="%.4f")
    op_lon = c6.number_input("Longitude", value=st.session_state.operator_lon, format="%.4f")
    
    c_lock, c_purge = st.columns([3, 1])
    
    if c_lock.button("💾 Lock in and save", use_container_width=True):
        st.session_state.operator_handle = op_handle.strip()
        st.session_state.operator_city = op_city.strip()
        st.session_state.operator_state = op_state.strip()
        st.session_state.operator_country = op_country.strip()
        st.session_state.operator_lat = op_lat
        st.session_state.operator_lon = op_lon
        
        st.session_state.profile_to_save = {
            "name": st.session_state.operator_handle,
            "city": st.session_state.operator_city,
            "state": st.session_state.operator_state,
            "country": st.session_state.operator_country,
            "lat": st.session_state.operator_lat,
            "lon": st.session_state.operator_lon
        }
        st.success("Location saved, you may now commence with submitting receptions!")
        
    if c_purge.button("🗑️ Clear Saved Profile", use_container_width=True):
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
    
elif nav_selection == "[ SUBMIT RECEPTION ]":
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
    
elif nav_selection == "[ MAPS & RADAR ]":
    st.write("Maps & Radar Under Construction...")
    
elif nav_selection == "[ RULES ]":
    st.write("Rules Under Construction...")
