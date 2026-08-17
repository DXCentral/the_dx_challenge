import streamlit as st
import pandas as pd
import numpy as np
import datetime
from modules.data_forge import calculate_haversine_distance, get_station_databases, get_gsheet

# =========================================================================
# 🎛️ THE BANDSCAN GRID (BASELINE MATRIX ENGINE)
# Interactive onboarding grid for mapping local baselines and daytime MW.
# =========================================================================

# Standard Frequency Definitions
MW_FREQUENCIES_10 = [str(freq) for freq in range(530, 1720, 10)]
MW_FREQUENCIES_9 = [str(freq) for freq in range(531, 1710, 9)] 
FM_FREQUENCIES = [f"{round(freq / 10.0, 1)}" for freq in range(881, 1081, 2)]
NWR_FREQUENCIES = [f"{f:.3f}" for f in [162.400, 162.425, 162.450, 162.475, 162.500, 162.525, 162.550]]

MW_LOCAL_CUTOFF_MILES = 100.0
AUTO_FETCH_RADIUS_MILES = 200.0

def initialize_bandscan_state(user_handle, mw_spacing):
    if "bandscan_data" not in st.session_state:
        st.session_state.bandscan_data = {"MW": {}, "FM": {}, "NWR": {}}
    
    mw_list = MW_FREQUENCIES_10 if mw_spacing == "10 kHz (Americas)" else MW_FREQUENCIES_9
    for f in mw_list:
        if f not in st.session_state.bandscan_data["MW"]:
            st.session_state.bandscan_data["MW"][f] = None
    for f in FM_FREQUENCIES:
        if f not in st.session_state.bandscan_data["FM"]:
            st.session_state.bandscan_data["FM"][f] = None
    for f in NWR_FREQUENCIES:
        if f not in st.session_state.bandscan_data["NWR"]:
            st.session_state.bandscan_data["NWR"][f] = None

def get_band_completion_stats(band, mw_spacing="10 kHz (Americas)"):
    grid = st.session_state.bandscan_data.get(band, {})
    if band == "MW":
        target_list = MW_FREQUENCIES_10 if mw_spacing == "10 kHz (Americas)" else MW_FREQUENCIES_9
        total = len(target_list)
        completed = sum(1 for k in target_list if grid.get(k) is not None)
    elif band == "FM":
        total = len(FM_FREQUENCIES)
        completed = sum(1 for k in FM_FREQUENCIES if grid.get(k) is not None)
    else:
        total = len(NWR_FREQUENCIES)
        completed = sum(1 for k in NWR_FREQUENCIES if grid.get(k) is not None)

    if total == 0: return 0, 0, 0.0
    pct = (completed / total) * 100.0
    return total, completed, pct

def standardize_active_db(band, mw_db, fm_db, nwr_db):
    """Normalizes the column names across all 3 DBs so they can be parsed by the local radar engine."""
    if band == "MW" and not mw_db.empty:
        df = mw_db.copy()
        df['S_FREQ'] = df['Frequency'].astype(str)
        df['S_CALL'] = df['Callsign']
        df['S_CITY'] = df['City']
        df['S_STATE'] = df['State']
        df['S_COUNTRY'] = df.get('Country', 'United States')
        df['S_COUNTY'] = df.get('County', ' - ')
        df['S_GRID'] = df.get('Grid', '')
        df['S_LAT'] = pd.to_numeric(df['LAT'], errors='coerce').fillna(0.0)
        df['S_LON'] = pd.to_numeric(df['LON'], errors='coerce').fillna(0.0)
        return df
    elif band == "FM" and not fm_db.empty:
        df = fm_db.copy()
        df['S_FREQ'] = pd.to_numeric(df['Frequency'], errors='coerce').round(1).astype(str)
        df['S_CALL'] = df['Callsign']
        df['S_CITY'] = df['City']
        df['S_STATE'] = df['State']
        df['S_COUNTRY'] = df.get('Country', 'United States')
        df['S_COUNTY'] = df.get('County', ' - ')
        df['S_GRID'] = df.get('Grid', '')
        df['S_LAT'] = pd.to_numeric(df['LAT'], errors='coerce').fillna(0.0)
        df['S_LON'] = pd.to_numeric(df['LON'], errors='coerce').fillna(0.0)
        return df
    elif band == "NWR" and not nwr_db.empty:
        df = nwr_db.copy()
        df['S_FREQ'] = pd.to_numeric(df['Frequency'], errors='coerce').apply(lambda x: f"{x:.3f}")
        df['S_CALL'] = df['Callsign']
        df['S_CITY'] = df['City']
        df['S_STATE'] = df['State']
        df['S_COUNTRY'] = df.get('Country', 'United States')
        df['S_COUNTY'] = df.get('County', ' - ')
        df['S_GRID'] = df.get('Grid', '')
        df['S_LAT'] = pd.to_numeric(df['LAT'], errors='coerce').fillna(0.0)
        df['S_LON'] = pd.to_numeric(df['LON'], errors='coerce').fillna(0.0)
        return df
    return pd.DataFrame()

def submit_to_master_log(band, freq, call, city, state, country, dist, grid="", county=""):
    """Silently pushes the intercept directly to the master Google Sheet as a live log."""
    sheet = get_gsheet()
    if sheet is None:
        st.error("🚨 DATALINK OFFLINE: Unable to connect to Master Sheet.")
        return False
        
    op = st.session_state.get('operator_profile', {})
    now = datetime.datetime.now(datetime.timezone.utc)
    
    band_mapped = "AM" if band == "MW" else band
    freq_am = freq if band == "MW" else ""
    freq_fm = freq if band != "MW" else ""
    prop = "Groundwave - Daytime" if band == "MW" else "Local"
    
    row_data = [
        op.get('name', ''), 
        op.get('city', ''), 
        op.get('state', ''), 
        op.get('country', 'United States'),
        band_mapped, 
        freq_am, 
        freq_fm, 
        call, 
        "", 
        city, 
        state, 
        country, 
        "", 
        grid,
        now.strftime("%m/%d/%Y"), 
        now.strftime("%H%M"), 
        round(float(dist), 1), 
        "Bandscan Auto-Log", 
        "No", 
        "", 
        prop, 
        county, 
        "HOME QTH", 
        "", 
        "",
        st.session_state.get("sticky_sdr", "Yes")
    ]
    
    try:
        sheet.append_row(["" if pd.isna(item) else (item.item() if hasattr(item, 'item') else item) for item in row_data])
        return True
    except Exception as e:
        st.error(f"Transmission to Master Log Failed: {e}")
        return False

def render_bandscan_grid(user_lat=None, user_lon=None, user_handle="Operator"):
    st.markdown("## 🧭 BANDSCAN GRID: BASELINE TRAINING")
    st.markdown("> Complete your local dial baseline scan to unlock challenge leaderboards and establish your station noise floor. Select a frequency to scan your local 200-mile radius.")

    band = st.radio("Select Bandscan Matrix:", ["MW", "FM", "NWR"], horizontal=True, index=0)

    mw_spacing = "10 kHz (Americas)"
    if band == "MW":
        mw_spacing = st.radio("Select MW Channel Spacing:", ["10 kHz (Americas)", "9 kHz (ITU Regions 1 & 3)"], horizontal=True)

    initialize_bandscan_state(user_handle, mw_spacing)
    mw_db, fm_db, nwr_db, intl_db = get_station_databases()
    
    # --- 1. The 200-Mile Local Radar Engine ---
    nearby_df = pd.DataFrame()
    std_db = standardize_active_db(band, mw_db, fm_db, nwr_db)
    
    if not std_db.empty and user_lat and user_lon:
        std_db['Dist_From_User'] = std_db.apply(lambda x: calculate_haversine_distance(user_lat, user_lon, x['S_LAT'], x['S_LON']), axis=1)
        nearby_df = std_db[(std_db['Dist_From_User'] > 0) & (std_db['Dist_From_User'] <= AUTO_FETCH_RADIUS_MILES)].copy()
        nearby_df = nearby_df.sort_values('Dist_From_User')

    total_channels, completed_channels, pct_done = get_band_completion_stats(band, mw_spacing)

    col_stat1, col_stat2, col_stat3 = st.columns([1, 1, 2])
    with col_stat1: st.metric(label=f"{band} Progress", value=f"{completed_channels} / {total_channels}")
    with col_stat2: st.metric(label="Status", value="UNLOCKED" if pct_done == 100.0 else "IN PROGRESS")
    with col_stat3: st.progress(pct_done / 100.0)

    st.divider()

    # --- 2. The Main Matrix Generation ---
    col_grid, col_radar = st.columns([2.5, 1])

    with col_radar:
        st.markdown(f"### 📡 LOCAL TARGETS (< {int(AUTO_FETCH_RADIUS_MILES)} mi)")
        if nearby_df.empty:
            st.info("No local targets found in databank.")
        else:
            view_nearby = nearby_df[['S_FREQ', 'S_CALL', 'S_CITY', 'Dist_From_User']].rename(columns={'S_FREQ': 'Freq', 'S_CALL': 'Call', 'S_CITY': 'City', 'Dist_From_User': 'Miles'})
            st.dataframe(view_nearby, hide_index=True, use_container_width=True)

    with col_grid:
        if band == "MW":
            freq_list = MW_FREQUENCIES_10 if mw_spacing == "10 kHz (Americas)" else MW_FREQUENCIES_9
            st.info("☀️ **MW Rule:** Scan during daytime conditions. Catches > 100 mi count as Daytime DX!")
        elif band == "FM":
            freq_list = FM_FREQUENCIES
            st.info("📡 **FM Rule:** Log your permanent daily locals. Empty channels must be marked as STATIC.")
        else:
            freq_list = NWR_FREQUENCIES
            st.info("🌩️ **NWR Rule:** Log your regular local weather stations across the 7 VHF frequencies.")

        cols_per_row = 5 if band != "NWR" else 7
        for row_idx in range(0, len(freq_list), cols_per_row):
            cols = st.columns(cols_per_row)
            for col_idx, col in enumerate(cols):
                item_idx = row_idx + col_idx
                if item_idx < len(freq_list):
                    freq_key = freq_list[item_idx]
                    val = st.session_state.bandscan_data[band].get(freq_key)

                    if val is None: btn_label = f"🔴 {freq_key}"
                    elif val.get("type") == "STATIC": btn_label = f"⚪ {freq_key}"
                    elif val.get("type") == "DX": btn_label = f"🌟 {freq_key} [{val.get('call')}]"
                    else: btn_label = f"🟢 {freq_key} [{val.get('call')}]"

                    if col.button(btn_label, key=f"btn_{band}_{freq_key}", use_container_width=True):
                        st.session_state[f"active_edit_{band}"] = freq_key

    # --- 3. The Auto-Fill & Dual-Log Drawer ---
    active_freq = st.session_state.get(f"active_edit_{band}")
    if active_freq:
        st.divider()
        st.subheader(f"⚙️ CONFIGURE BASELINE: {active_freq} {'kHz' if band == 'MW' else 'MHz'}")

        current_entry = st.session_state.bandscan_data[band].get(active_freq) or {}

        # SMART RADAR LIST: Pull stations within 200 miles on this exact frequency
        if not nearby_df.empty:
            matches = nearby_df[nearby_df['S_FREQ'] == active_freq]
            if not matches.empty:
                st.markdown(f"#### 🎯 DETECTED TARGETS ON {active_freq}")
                st.write("Click a station below to lock it as your baseline and instantly transmit the log to the Master Sheet:")
                
                for _, match in matches.iterrows():
                    btn_label = f"📡 {match['S_CALL']} — {match['S_CITY']}, {match['S_STATE']} ({match['Dist_From_User']:.1f} mi)"
                    if st.button(btn_label, key=f"auto_{band}_{active_freq}_{match['S_CALL']}", use_container_width=True):
                        
                        station_type = "DX" if (band == "MW" and match['Dist_From_User'] >= MW_LOCAL_CUTOFF_MILES) else "LOCAL"
                        
                        st.session_state.bandscan_data[band][active_freq] = {
                            "type": station_type, 
                            "call": match['S_CALL'], 
                            "city": match['S_CITY'], 
                            "state": match['S_STATE'], 
                            "distance": match['Dist_From_User']
                        }
                        
                        with st.spinner("TRANSMITTING TO MASTER DATABANK..."):
                            success = submit_to_master_log(
                                band=band, 
                                freq=active_freq, 
                                call=match['S_CALL'], 
                                city=match['S_CITY'], 
                                state=match['S_STATE'], 
                                country=match['S_COUNTRY'], 
                                dist=match['Dist_From_User'],
                                grid=match['S_GRID'],
                                county=match['S_COUNTY']
                            )
                            
                        if success:
                            st.success(f"✅ TARGET LOCKED & TRANSMITTED: {match['S_CALL']} logged as {station_type} baseline.")
                            st.rerun()

        # MANUAL FALLBACK & STATIC ENTRY
        st.markdown("---")
        st.markdown("#### MANUAL OVERRIDE")
        st.write("If your target is outside the 200-mile radar sweep or the frequency is dead air, use the manual override below.")
        
        with st.form(key=f"form_bandscan_{band}_{active_freq}"):
            c_stat, c_btn = st.columns([1, 1])
            is_static = c_stat.checkbox("No dominant signal (Mark as STATIC)", value=(current_entry.get("type") == "STATIC"))

            c1, c2, c3 = st.columns(3)
            call_input = c1.text_input("Callsign:", value=current_entry.get("call", "") if current_entry.get("call") != "STATIC" else "", disabled=is_static).strip().upper()
            city_input = c2.text_input("City:", value=current_entry.get("city", "") if current_entry.get("city") != "N/A" else "", disabled=is_static).strip()
            state_input = c3.text_input("State:", value=current_entry.get("state", "") if current_entry.get("state") != "N/A" else "", disabled=is_static).strip().upper()

            if st.form_submit_button("SAVE MANUAL OVERRIDE (Local Baseline Only)"):
                if is_static:
                    st.session_state.bandscan_data[band][active_freq] = {"type": "STATIC", "call": "STATIC", "city": "N/A", "state": "N/A", "distance": 0.0}
                    st.rerun()
                elif call_input:
                    matched_dist, station_type = 0.0, "LOCAL"

                    if not std_db.empty:
                        matched = std_db[(std_db["S_FREQ"] == active_freq) & (std_db["S_CALL"].str.upper() == call_input)]
                        if not matched.empty and user_lat and user_lon:
                            st_lat, st_lon = matched.iloc[0].get("S_LAT"), matched.iloc[0].get("S_LON")
                            matched_dist = calculate_haversine_distance(user_lat, user_lon, st_lat, st_lon)
                            if band == "MW" and matched_dist >= MW_LOCAL_CUTOFF_MILES:
                                station_type = "DX"

                    st.session_state.bandscan_data[band][active_freq] = {"type": station_type, "call": call_input, "city": city_input, "state": state_input, "distance": matched_dist}
                    st.success(f"Frequency {active_freq} logged as {station_type} ({call_input} - {matched_dist} mi). (Not sent to master log).")
                    st.rerun()
                else:
                    st.warning("Please provide a callsign or check the STATIC box.")
