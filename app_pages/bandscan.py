from __future__ import annotations

import pandas as pd
import streamlit as st

from app_support import get_store, require_location
from dxcore.bandscan import reception_history
from dxcore.stations import frequencies_for_band


COLORS = {
    "local": "#E24A5A",
    "regional": "#F28C28",
    "open": "#39C986",
}
DISTANCE_FILTERS = {
    "All": None,
    "Red · within 50 mi": "local",
    "Orange · 50–200 mi": "regional",
    "Green · beyond 200 mi": "open",
}


def frequency_label(band: str, value: float) -> str:
    if band == "MW":
        return f"{int(value)} kHz"
    return f"{value:.3f} MHz" if band == "NWR" else f"{value:.1f} MHz"


st.title("Bandscan")
st.caption(
    "Explore your submitted reception history by frequency. Bandscan is optional and never restricts log entry."
)

location = require_location()
user_id = st.session_state.user["user_id"]
logs = get_store().logs(user_id)

band = st.segmented_control(
    "Band",
    ["MW", "FM", "NWR"],
    default="MW" if "scan_band" not in st.session_state else None,
    key="scan_band",
    persist_state="session",
)
mw_spacing = "10 kHz"
if band == "MW":
    mw_spacing = st.segmented_control(
        "MW channel spacing",
        ["10 kHz", "9 kHz"],
        default="10 kHz" if "scan_mw_spacing" not in st.session_state else None,
        key="scan_mw_spacing",
        persist_state="session",
    )

frequencies = frequencies_for_band(band, mw_spacing)
history = reception_history(
    logs,
    band=band,
    location_id=str(location["location_id"]),
)
band_rows = (
    logs[
        (logs["band"].astype(str).str.upper() == band)
        & (logs["location_id"].astype(str) == str(location["location_id"]))
    ]
    if not logs.empty
    else pd.DataFrame()
)

with st.container(horizontal=True):
    st.metric("Frequencies heard", f"{len(history):,}", border=True)
    unique_stations = int(band_rows["station_id"].nunique()) if not band_rows.empty else 0
    st.metric("Unique stations", f"{unique_stations:,}", border=True)
    st.metric("Submitted receptions", f"{len(band_rows):,}", border=True)

st.caption(
    ":red-badge[Red · station within 50 mi] "
    ":orange-badge[Orange · station within 200 mi] "
    ":green-badge[Green · only stations beyond 200 mi]"
)

filter_key = f"scan_distance_filter_{band}"
st.session_state.setdefault(filter_key, "All")
with st.container(horizontal=True, vertical_alignment="bottom"):
    distance_filter = st.segmented_control(
        "Filter frequency grid by distance category",
        list(DISTANCE_FILTERS),
        key=filter_key,
        persist_state="session",
    )
    if st.button(
        "Clear distance filter",
        icon=":material/filter_alt_off:",
        disabled=distance_filter == "All",
        key=f"clear_scan_distance_{band}",
    ):
        st.session_state[filter_key] = "All"
        st.rerun()

style_rules: list[str] = []
frequency_keys = {round(value, 3) for value in frequencies}
selected_level = DISTANCE_FILTERS.get(distance_filter)
for frequency in frequency_keys:
    summary = history.get(frequency)
    token = str(frequency).replace(".", "_")
    if summary:
        border_color = COLORS[str(summary["interference"])]
        style_rules.append(
            f".st-key-scan_{band}_{token} button {{"
            f"background-color:transparent !important; color:var(--dx-text) !important; "
            f"border:2px solid {border_color} !important; font-weight:600;}}"
        )
    if selected_level is not None and (
        summary is None or str(summary["interference"]) != selected_level
    ):
        style_rules.append(
            f".st-key-scan_{band}_{token} {{opacity:.25; filter:grayscale(.85);}}"
        )
if style_rules:
    st.html(f"<style>{''.join(style_rules)}</style>")

st.subheader("Frequency matrix")
for start in range(0, len(frequencies), 7):
    columns = st.columns(7, gap="small", wrap=True)
    for column, frequency in zip(columns, frequencies[start : start + 7], strict=False):
        key = round(float(frequency), 3)
        summary = history.get(key)
        count = int(summary["unique_stations"]) if summary else 0
        label = frequency_label(band, frequency) + (f" ({count})" if count else "")
        token = str(key).replace(".", "_")
        if column.button(label, key=f"scan_{band}_{token}", width="stretch"):
            st.session_state[f"scan_active_frequency_{band}"] = key

active_frequency = st.session_state.get(f"scan_active_frequency_{band}")
if active_frequency not in frequency_keys:
    active_frequency = None

with st.sidebar:
    st.subheader("Frequency history")
    if active_frequency is None:
        st.caption("Choose a frequency in the matrix to see your submitted receptions.")
    else:
        st.markdown(f"**{frequency_label(band, float(active_frequency))}**")
        summary = history.get(float(active_frequency))
        if not summary:
            st.caption("No stations have been logged on this frequency from the selected QTH.")
        else:
            rows = summary["rows"].copy()
            rows["station_key"] = rows["station_id"].fillna("").astype(str)
            blank = rows["station_key"].str.strip() == ""
            rows.loc[blank, "station_key"] = (
                rows.loc[blank, "call"].fillna("").astype(str)
                + "|"
                + rows.loc[blank, "station_city"].fillna("").astype(str)
                + "|"
                + rows.loc[blank, "station_region"].fillna("").astype(str)
            )
            st.caption(
                f"{int(summary['unique_stations']):,} unique station(s) · {len(rows):,} reception(s)"
            )
            for _, station_rows in rows.groupby("station_key", sort=False):
                first = station_rows.iloc[0]
                location_parts = [
                    str(first.get("station_city", "")).strip(),
                    str(first.get("station_region", "")).strip(),
                    str(first.get("station_country", "")).strip(),
                ]
                station_location = ", ".join(part for part in location_parts if part)
                with st.container(border=True):
                    st.markdown(f"**{first['call']}**")
                    if station_location:
                        st.caption(station_location)
                    receptions = pd.to_datetime(
                        station_rows["reception_utc"], utc=True, errors="coerce"
                    )
                    for (_, reception_row), instant in zip(
                        station_rows.iterrows(), receptions, strict=False
                    ):
                        when = (
                            instant.strftime("%Y-%m-%d %H:%M UTC")
                            if not pd.isna(instant)
                            else str(reception_row.get("reception_utc", ""))
                        )
                        propagation = str(reception_row.get("propagation", "")).strip() or "Unspecified"
                        st.markdown(f"- {when} · {propagation}")
