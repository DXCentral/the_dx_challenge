import streamlit as st
import datetime
from modules.data_forge import get_station_databases, calculate_haversine_distance, get_maidenhead_grid

# =========================================================================
# 📝 THE SUBMISSION CONSOLE
# Unified entry form for MW, FM, and NWR logs with dynamic DB lookups.
# =========================================================================

def render_submission_console(user_lat, user_lon, user_handle):
    st.markdown("## 📡 LIVE LOG SUBMISSION")
    st.markdown("> Enter your DX catches here. All times must be strictly in UTC.")

    # Load databases from RAM
    mw_db, fm_db, nwr_db, intl_db = get_station_databases()

    band = st.radio("Select Band", ["MW", "FM", "NWR"], horizontal=True)

    with st.form("log_submission_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            log_date = st.date_input("Date of Reception (UTC)", datetime.datetime.now(datetime.timezone.utc).date())
            
            # Dynamic Frequency Inputs based on Band
            if band == "MW":
                freq = st.number_input("Frequency (kHz)", min_value=530, max_value=1720, step=9)
            elif band == "FM":
                freq = st.number_input("Frequency (MHz)", min_value=87.5, max_value=107.9, step=0.2, format="%.1f")
            else:
                freq = st.selectbox("Frequency (MHz)", [162.400, 162.425, 162.450, 162.475, 162.500, 162.525, 162.550])

        with col2:
            log_time = st.time_input("Time of Reception (UTC)", datetime.datetime.now(datetime.timezone.utc).time())
            callsign = st.text_input("Callsign / Station ID").strip().upper()

        # Propagation Mode selection (crucial for VHF Specialists)
        prop_mode = "Skywave/Groundwave"
        if band in ["FM", "NWR"]:
            prop_mode = st.selectbox(
                "Propagation Mode", 
                ["Tropo", "Meteor Scatter", "Sporadic E (Es)", "Aurora", "Aircraft Scatter", "Other"]
            )

        submit_btn = st.form_submit_button("VALIDATE & SUBMIT LOG")

        if submit_btn:
            if not callsign:
                st.error("⚠️ Callsign is required to process a log.")
                return

            # ---------------------------------------------------------
            # DATABASE LOOKUP & MATH ENGINE
            # ---------------------------------------------------------
            match = None
            if band == "MW" and not mw_db.empty:
                dom_match = mw_db[(mw_db["FREQ"] == freq) & (mw_db["CALL"].str.upper() == callsign)]
                if not dom_match.empty:
                    match = dom_match.iloc[0]
            elif band == "FM" and not fm_db.empty:
                # Note: WTFDA frequency column might be float; handle rounding if necessary
                fm_match = fm_db[(fm_db["Frequency"] == freq) & (fm_db["Callsign"].str.upper() == callsign)]
                if not fm_match.empty:
                    match = fm_match.iloc[0]
            elif band == "NWR" and not nwr_db.empty:
                nwr_match = nwr_db[(nwr_db["FREQ"] == freq) & (nwr_db["CALLSIGN"].str.upper() == callsign)]
                if not nwr_match.empty:
                    match = nwr_match.iloc[0]

            if match is not None:
                # Extract coordinates and metadata based on band schema
                st_lat, st_lon = 0.0, 0.0
                city, state, fips = "Unknown", "Unknown", ""
                
                if band == "MW":
                    st_lat, st_lon = match.get("LAT", 0), match.get("LON", 0)
                    city, state = match.get("CITY", ""), match.get("STATE", "")
                elif band == "FM":
                    st_lat, st_lon = match.get("Decimal_Lat", 0), match.get("Decimal_Lon", 0)
                    city, state = match.get("City", ""), match.get("S/P", "")
                elif band == "NWR":
                    st_lat, st_lon = match.get("LAT", 0), match.get("LON", 0)
                    city, state = match.get("SITELOC", ""), match.get("ST", "")

                # Run Geospatial Math
                distance = calculate_haversine_distance(user_lat, user_lon, st_lat, st_lon)
                grid = get_maidenhead_grid(st_lat, st_lon)

                st.success(f"✅ Station Identified: {city}, {state} | Distance: {distance} miles | Grid: {grid}")
                st.info("Log validated! (Ready to transmit payload to Master Google Sheet)")
                
                # Payload construction for gspread will go here
            else:
                st.warning(f"⚠️ Station {callsign} on {freq} not found in the {band} database. Double-check your entry or proceed with a manual override.")
