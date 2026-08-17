import pandas as pd
import numpy as np
import datetime
import streamlit as st
import math

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


# ---------------------------------------------------------
# 2. CACHED DATA LOADERS (In-Memory Processing)
# ---------------------------------------------------------

@st.cache_data(ttl=300)
def load_all_time_master_df():
    """
    Fetches the live Season 7 Sheet and the Legacy CSV.
    Concatenates them into a single in-memory All-Time dataframe.
    """
    try:
        df_live = pd.read_csv(URL_SEASON_7_LIVE)
        df_legacy = pd.read_csv(URL_LEGACY_MASTER)
        
        # Standardize UTC reception timestamps
        if 'Date of Reception (UTC)' in df_live.columns:
            df_live['Date of Reception (UTC)'] = pd.to_datetime(df_live['Date of Reception (UTC)'], errors='coerce')
        if 'Date of Reception (UTC)' in df_legacy.columns:
            df_legacy['Date of Reception (UTC)'] = pd.to_datetime(df_legacy['Date of Reception (UTC)'], errors='coerce')

        # Combine historical records with live entries
        df_master = pd.concat([df_legacy, df_live], ignore_index=True)
        return df_master
        
    except Exception as e:
        st.error(f"SYSTEM ALERT: Failed to load Master Database. Error: {e}")
        return pd.DataFrame()


@st.cache_data
def get_station_databases():
    """
    Loads all reference station databases into memory.
    Cached indefinitely per runtime session.
    """
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
# 3. GEOSPATIAL & ASTRONOMICAL UTILITIES
# ---------------------------------------------------------

def calculate_haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculates the great-circle distance between two coordinates in Miles.
    """
    try:
        lat1, lon1, lat2, lon2 = map(float, [lat1, lon1, lat2, lon2])
    except (ValueError, TypeError):
        return 0.0

    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    radius_earth_miles = 3958.8
    distance = radius_earth_miles * c
    
    return round(distance, 1)


def get_maidenhead_grid(lat, lon):
    """
    Converts decimal latitude and longitude into a 6-character Maidenhead Grid locator.
    """
    try:
        lat, lon = float(lat), float(lon)
    except (ValueError, TypeError):
        return ""

    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return ""

    lon += 180.0
    lat += 90.0

    field_lon = chr(ord('A') + int(lon / 20))
    field_lat = chr(ord('A') + int(lat / 10))

    square_lon = str(int((lon % 20) / 2))
    square_lat = str(int((lat % 10) / 1))

    sub_lon = chr(ord('a') + int((lon - int(lon / 2) * 2) / (5.0 / 60.0)))
    sub_lat = chr(ord('a') + int((lat - int(lat / 1) * 1) / (2.5 / 60.0)))

    return f"{field_lon}{field_lat}{square_lon}{square_lat}{sub_lon}{sub_lat}".upper()
