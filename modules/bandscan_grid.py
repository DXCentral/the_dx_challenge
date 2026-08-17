import streamlit as st
import pandas as pd
import numpy as np
from modules.data_forge import calculate_haversine_distance, get_station_databases

# =========================================================================
# 🎛️ THE BANDSCAN GRID (BASELINE MATRIX ENGINE)
# Interactive onboarding grid for mapping local baselines and daytime MW.
# =========================================================================

# Standard Frequency Definitions
MW_FREQUENCIES_10 = [str(freq) for freq in range(530, 1720, 10)]
MW_FREQUENCIES_9 = [str(freq) for freq in range(531, 1710, 9)] # 531 to 1701 kHz
FM_FREQUENCIES = [f"{round(freq / 10.0, 1)}" for freq in range(881, 1081, 2)]
NWR_FREQUENCIES = [f"{f:.3f}" for f in [162.400, 162.425, 162.450, 162.475, 162.500, 162.525, 162.550]]

MW_LOCAL_CUTOFF_MILES = 100.0


def initialize_bandscan_state(user_handle, mw_spacing):
    """Initializes session memory for the user's bandscan progress."""
    if "bandscan_data" not in st.session_state:
        st.session_state.bandscan_data = {"MW": {}, "FM": {}, "NWR": {}}
    
    # Initialize MW based on the selected spacing
    mw_list = MW_FREQUENCIES_10 if mw_spacing == "10 kHz (Americas)" else MW_FREQUENCIES_9
    for f in mw_list:
        if f not in st.session_state.bandscan_data["MW"]:
            st.session_state.bandscan_data["MW"][f] = None
            
    # Initialize VHF
    for f in FM_FREQUENCIES:
        if f not in st.session_state.bandscan_data["FM"]:
            st.session_state.bandscan_data["FM"][f] = None
    for f in NWR_FREQUENCIES:
        if f not in st.session_state.bandscan_data["NWR"]:
            st.session_state.bandscan_data["NWR"][f] = None


def get_band_completion_stats(band, mw_spacing="10 kHz (Americas)"):
    """Calculates total, completed, and percentage done for a given band."""
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

    if total == 0:
        return 0, 0, 0.0
    pct = (completed / total) * 100.0
    return total, completed, pct


def render_bandscan_grid(user_lat=None, user_lon=None, user_handle="Operator"):
    """Renders the main Bandscan Grid UI."""
    st.markdown("## 🧭 BANDSCAN GRID: BASELINE TRAINING")
    st.markdown(
        "> Complete your local dial baseline scan to unlock challenge leaderboards "
        "and establish your station noise floor. Enter your local/semi-local catch or mark as **STATIC**."
    )

    band = st.radio(
        "Select Bandscan Matrix:",
        ["MW", "FM", "NWR"],
        horizontal=True,
        index=0,
        help="Select the RF band to map out.",
    )

    mw_spacing = "10 kHz (Americas)"
    if band == "MW":
        mw_spacing = st.radio(
            "Select MW Channel Spacing:",
            ["10 kHz (Americas)", "9 kHz (ITU Regions 1 & 3)"],
            horizontal=True
        )

    initialize_bandscan_state(user_handle, mw_spacing)
    mw_db, fm_db, nwr_db, intl_db = get_station_databases()

    total_channels, completed_channels, pct_done = get_band_completion_stats(band, mw_spacing)

    # Progress Overview
    col_stat1, col_stat2, col_stat3 = st.columns([1, 1, 2])
    with col_stat1:
        st.metric(label=f"{band} Progress", value=f"{completed_channels} / {total_channels}")
    with col_stat2:
        status_label = "UNLOCKED" if pct_done == 100.0 else "IN PROGRESS"
        st.metric(label="Status", value=status_label)
    with col_stat3:
        st.progress(pct_done / 100.0)

    st.divider()

    # Active Grid Frequencies
    if band == "MW":
        freq_list = MW_FREQUENCIES_10 if mw_spacing == "10 kHz (Americas)" else MW_FREQUENCIES_9
        st.info("☀️ **MW Rule:** Scan during daytime conditions (between local sunrise & sunset). Catches > 100 mi count as Daytime DX!")
    elif band == "FM":
        freq_list = FM_FREQUENCIES
        st.info("📡 **FM Rule:** Log your permanent daily locals. Empty channels must be marked as STATIC.")
    else:
        freq_list = NWR_FREQUENCIES
        st.info("🌩️ **NWR Rule:** Log your regular local weather stations across the 7 VHF frequencies.")

    # Render Grid Buttons & Entry Expansion
    cols_per_row = 6 if band != "NWR" else 7
    for row_idx in range(0, len(freq_list), cols_per_row):
        cols = st.columns(cols_per_row)
        for col_idx, col in enumerate(cols):
            item_idx = row_idx + col_idx
            if item_idx < len(freq_list):
                freq_key = freq_list[item_idx]
                val = st.session_state.bandscan_data[band].get(freq_key)

                if val is None:
                    btn_label = f"🔴 {freq_key}"
                elif val.get("type") == "STATIC":
                    btn_label = f"⚪ {freq_key} [ST]"
                elif val.get("type") == "DX":
                    btn_label = f"🌟 {freq_key} [{val.get('call')}]"
                else:
                    btn_label = f"🟢 {freq_key} [{val.get('call')}]"

                if col.button(btn_label, key=f"btn_{band}_{freq_key}", use_container_width=True):
                    st.session_state[f"active_edit_{band}"] = freq_key

    # Modal/Drawer Editor for Selected Frequency
    active_freq = st.session_state.get(f"active_edit_{band}")
    if active_freq:
        st.divider()
        st.subheader(f"⚙️ Configure Baseline: {active_freq} {'kHz' if band == 'MW' else 'MHz'}")

        current_entry = st.session_state.bandscan_data[band].get(active_freq) or {}

        with st.form(key=f"form_bandscan_{band}_{active_freq}"):
            is_static = st.checkbox("No dominant signal (Mark as STATIC)", value=(current_entry.get("type") == "STATIC"))

            call_input = st.text_input(
                "Station Callsign / ID:",
                value=current_entry.get("call", ""),
                disabled=is_static,
                placeholder="e.g. WWL, WWNO, KHB43",
            ).strip().upper()

            city_input = st.text_input(
                "City of License / Transmitter Site:",
                value=current_entry.get("city", ""),
                disabled=is_static,
                placeholder="e.g. New Orleans",
            ).strip()

            state_input = st.text_input(
                "State / Territory:",
                value=current_entry.get("state", ""),
                disabled=is_static,
                placeholder="e.g. LA",
            ).strip().upper()

            submit_btn = st.form_submit_button("Save Frequency Baseline")

            if submit_btn:
                if is_static:
                    st.session_state.bandscan_data[band][active_freq] = {
                        "type": "STATIC",
                        "call": "STATIC",
                        "city": "N/A",
                        "state": "N/A",
                        "distance": 0.0,
                    }
                    st.success(f"Frequency {active_freq} logged as STATIC baseline.")
                    st.rerun()
                elif call_input:
                    matched_dist = 0.0
                    station_type = "LOCAL"

                    if band == "MW" and not mw_db.empty:
                        matched = mw_db[(mw_db["FREQ"].astype(str) == active_freq) & (mw_db["CALL"].str.upper() == call_input)]
                        if not matched.empty and user_lat and user_lon:
                            st_lat = matched.iloc[0].get("LAT")
                            st_lon = matched.iloc[0].get("LON")
                            matched_dist = calculate_haversine_distance(user_lat, user_lon, st_lat, st_lon)
                            if matched_dist >= MW_LOCAL_CUTOFF_MILES:
                                station_type = "DX"

                    st.session_state.bandscan_data[band][active_freq] = {
                        "type": station_type,
                        "call": call_input,
                        "city": city_input,
                        "state": state_input,
                        "distance": matched_dist,
                    }
                    st.success(f"Frequency {active_freq} logged as {station_type} ({call_input} - {matched_dist} mi)!")
                    st.rerun()
                else:
                    st.warning("Please provide a callsign or check the STATIC box.")
