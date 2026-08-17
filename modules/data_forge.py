import pandas as pd
import numpy as np
import datetime
import streamlit as st
import math
import gspread
from google.oauth2.service_account import Credentials
import maidenhead as mh
from geopy.geocoders import Nominatim

# =========================================================================
# ⚙️ THE DATA FORGE: SEASON 7 ENGINE
# Bypasses slow APIs by loading raw CSVs directly into RAM.
# =========================================================================

# ---------------------------------------------------------
# 1. DATABASE & LOGGING URLs 
# ---------------------------------------------------------

# LIVE SEASON 7 SPREADSHEET (Published to Web CSV)
URL_SEASON_7_LIVE = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSA-WRrT9dn9J_IVXbLdqExhyo7a0zavrOr39whb81J_NK7IXTAQUKUfc1Ig5cHlN6-Wa56JnYzlnoJ/pub?gid=0&single=true&output=csv"

# LEGACY MASTER (Seasons 1-5 Historical CSV)
URL_LEGACY_MASTER = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRYAzma6QCeDctqaPjc1BObXh05cegPaQEHvYZ_AmAt7ajxYSkcBs8dAzn4TcunrMQlySOVAC5Od9ne/pub?gid=0&single=true&output=csv"

# STATION REFERENCE DATABASES (Raw GitHub Endpoints)
URL_MW_DB   = "https://raw.githubusercontent.com/DXCentral/the_dx_challenge/15ddcd12d3f2a99efab06eee28d324eb134475d9/Mesa_Mike_Season_7_Enriched.csv"
URL_FM_DB   = "https://raw.githubusercontent.com/DXCentral/the_dx_challenge/15ddcd12d3f2a99efab06eee28d324eb134475d9/WTFDA_Season_7_Enriched.csv"
URL_NWR_DB  = "https://raw.githubusercontent.com/DXCentral/the_dx_challenge/15ddcd12d3f2a99efab06eee28d324eb134475d9/NWR_Transmitters_Cleaned.csv"
URL_INTL_DB = "https://raw.githubusercontent.com/DXCentral/the_dx_challenge/15ddcd12d3f2a99efab06eee28d324eb134475d9/MW%20International%20Station%20List%20-%20Season%207%20-%20081626%20-%20Season%207%20International%20Station%20List.csv"

# GOOGLE SHEETS WRITE CREDENTIALS (Make sure this ID matches the Season 7 Sheet!)
GSHEET_KEY = "11_4lKQRCrV2Q0YZM1syECgoSINmnGIG3k6UJH0m_u3Y"
GSHEET_TAB_NAME = "Form Entries"


# ---------------------------------------------------------
# 2. GOOGLE SHEETS UPLINK (For Writing Logs)
# ---------------------------------------------------------
def get_gsheet():
    """Securely connects to Google Sheets via Streamlit Secrets for writing payload data."""
    try:
        if "gcp_service_account" not in st.secrets: 
            return None
        scope = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        return client.open_by_key(GSHEET_KEY).worksheet(GSHEET_TAB_NAME)
    except Exception as e: 
        print(f"GSpread Uplink Error: {e}")
        return None


# ---------------------------------------------------------
# 3. CACHED DATA LOADERS (In-Memory Processing)
# ---------------------------------------------------------
@st.cache_data(ttl=300)
def load_all_time_master_df():
    """Fetches the live Season 7 Sheet and the Legacy CSV into RAM."""
    try:
        df_live = pd.read_csv(URL_SEASON_7_LIVE, dtype=str)
        df_legacy = pd.read_csv(URL_LEGACY_MASTER, dtype=str)
        
        # Standardize UTC reception timestamps
        if 'Date of Reception (UTC)' in df_live.columns:
            df_live['Date of Reception (UTC)'] = pd.to_datetime(df_live['Date of Reception (UTC)'], errors='coerce')
        if 'Date of Reception (UTC)' in df_legacy.columns:
            df_legacy['Date of Reception (UTC)'] = pd.to_datetime(df_legacy['Date of Reception (UTC)'], errors='coerce')

        df_master = pd.concat([df_legacy, df_live], ignore_index=True)
        return df_master
        
    except Exception as e:
        st.error(f"SYSTEM ALERT: Failed to load Master Database. Error: {e}")
        return pd.DataFrame()


@st.cache_data
def get_station_databases():
    """Loads all reference station databases into memory."""
    try:
        mw_db = pd.read_csv(URL_MW_DB)
        fm_db = pd.read_csv(URL_FM_DB)
        nwr_db = pd.read_csv(URL_NWR_DB)
        intl_db = pd.read_csv(URL_INTL_DB)
        return mw_db, fm_db, nwr_db, intl_db
    except Exception as e:
        st.error(f"SYSTEM ALERT: Failed to fetch reference databases. Error: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()


# ---------------------------------------------------------
# 4. GEOSPATIAL & ASTRONOMICAL UTILITIES
# ---------------------------------------------------------
def calculate_haversine_distance(lat1, lon1, lat2, lon2):
    """Calculates the great-circle distance between two coordinates in Miles."""
    try:
        lat1, lon1, lat2, lon2 = map(float, [lat1, lon1, lat2, lon2])
        if (lat1 == 0.0 and lon1 == 0.0) or (lat2 == 0.0 and lon2 == 0.0):
            return 0.0
    except (ValueError, TypeError):
        return 0.0

    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    radius_earth_miles = 3958.8
    return round(radius_earth_miles * c, 1)

def get_maidenhead_grid(lat, lon):
    """Converts decimal latitude and longitude into a 6-character Maidenhead Grid locator."""
    try:
        lat, lon = float(lat), float(lon)
        if lat == 0.0 and lon == 0.0: return ""
        return mh.to_maiden(lat, lon)
    except Exception:
        return ""

def get_lat_lon_from_grid(grid):
    """Converts a Maidenhead Grid to Decimal Coordinates."""
    try:
        lat, lon = mh.to_location(grid.strip())
        return float(lat), float(lon)
    except Exception:
        return None, None

def get_lat_lon_from_city(query):
    """Uses OpenStreetMap Nominatim to geocode a City/State."""
    try:
        geolocator = Nominatim(user_agent="dx_central_s7", timeout=5)
        loc = geolocator.geocode(query)
        if loc:
            return float(loc.latitude), float(loc.longitude)
    except Exception:
        pass
    return None, None
