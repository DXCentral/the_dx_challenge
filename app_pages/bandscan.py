from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from app_support import bandscan_progress, get_store, require_location
from dxcore.stations import frequencies_for_band, stations_on_frequency


def frequency_label(band: str, value: float) -> str:
    if band == "MW":
        return f"{int(value)} kHz"
    return f"{value:.3f} MHz" if band == "NWR" else f"{value:.1f} MHz"


st.title("Bandscan")
st.caption("Review every channel as a heard station or OPEN. Unreviewed channels remain red and locked.")

location = require_location()
store = get_store()
user_id = st.session_state.user["user_id"]

band = st.segmented_control("Band", ["MW", "FM", "NWR"], default="MW", key="scan_band")
mw_spacing = "10 kHz"
if band == "MW":
    mw_spacing = st.segmented_control(
        "MW channel spacing", ["10 kHz", "9 kHz"], default="10 kHz", key="scan_mw_spacing"
    )
frequencies = frequencies_for_band(band, mw_spacing)
scan = store.bandscan(user_id, str(location["location_id"]), band)
records = {round(float(row["frequency"]), 3): row for row in scan.to_dict("records")}
completed, total, ratio = bandscan_progress(str(location["location_id"]), band, mw_spacing)

with st.container(horizontal=True):
    st.metric(f"{band} readiness", f"{completed} / {total}", border=True)
    st.metric("Status", "Unlocked" if ratio == 1 else "In progress", border=True)
st.progress(ratio, text=f"{ratio:.0%} reviewed at {location['label']}")


@st.dialog("Mark remaining frequencies OPEN")
def confirm_fill_open() -> None:
    remaining = total - completed
    st.warning(
        f"Mark all {remaining:,} unreviewed {band} frequencies OPEN at {location['label']}?"
    )
    st.caption(
        "Existing station and OPEN results will not be overwritten. Use this only after confirming that no station is present on every remaining channel."
    )
    if st.button("Mark remaining OPEN", icon=":material/done_all:", type="primary"):
        store.fill_bandscan_open(user_id, str(location["location_id"]), band, frequencies)
        st.toast(f"All remaining {band} channels were marked OPEN.")
        st.rerun()


if st.button(
    "Mark all other frequencies OPEN",
    icon=":material/done_all:",
    disabled=completed >= total,
):
    confirm_fill_open()

style_rules = []
for frequency in frequencies:
    token = str(frequency).replace(".", "_")
    color = "#16794B" if round(frequency, 3) in records else "#A52B38"
    style_rules.append(
        f".st-key-scan_{band}_{token} button {{border-color:{color}; box-shadow:inset 0 -3px 0 {color};}}"
    )
st.html(f"<style>{''.join(style_rules)}</style>")

st.subheader("Channel matrix")
for start in range(0, len(frequencies), 7):
    columns = st.columns(7, gap="small", wrap=True)
    for column, frequency in zip(columns, frequencies[start : start + 7], strict=False):
        key = round(frequency, 3)
        saved = records.get(key)
        status = "EMPTY" if saved is None else (saved["call"] or saved["status"])
        token = str(frequency).replace(".", "_")
        if column.button(
            f"{frequency_label(band, frequency)} · {status}",
            key=f"scan_{band}_{token}",
            width="stretch",
        ):
            st.session_state[f"scan_active_frequency_{band}"] = frequency

active_frequency = st.session_state.get(f"scan_active_frequency_{band}")
if active_frequency not in frequencies:
    active_frequency = None

if active_frequency is None:
    st.info("Select a frequency to open its review drawer on the left.", icon=":material/swipe_left:")

with st.sidebar:
    st.subheader("Bandscan review")
    if active_frequency is None:
        st.caption("Choose an EMPTY or completed frequency in the channel matrix.")
    else:
        st.markdown(f"**{frequency_label(band, active_frequency)}**")
        show_all = st.toggle("Expand beyond 200 miles", key=f"scan_expand_{band}")
        radius = None if show_all else 200
        matches = stations_on_frequency(
            band,
            active_frequency,
            float(location["latitude"]),
            float(location["longitude"]),
            radius_miles=radius,
        )
        st.session_state.setdefault("bandscan_is_sdr", False)
        st.session_state.setdefault("bandscan_is_portable", not bool(location["is_home"]))
        is_sdr = st.checkbox("Received using an SDR", key="bandscan_is_sdr", persist_state="session")
        is_portable = st.checkbox("Portable operation", key="bandscan_is_portable", persist_state="session")

        if st.button("Mark OPEN", icon=":material/radio_button_unchecked:", type="primary"):
            store.save_bandscan(
                user_id, str(location["location_id"]), band, active_frequency, "OPEN", call="OPEN"
            )
            st.toast(f"{frequency_label(band, active_frequency)} marked OPEN")
            st.rerun()
        st.caption("OPEN means the channel was reviewed and no station was heard.")

        if matches.empty:
            st.info("No listed stations were found for this frequency and distance range.")
        else:
            station_view = matches[["call", "city", "region", "distance_miles"]].rename(
                columns={
                    "call": "Station",
                    "city": "City",
                    "region": "State / province",
                    "distance_miles": "Miles",
                }
            )
            event = st.dataframe(
                station_view,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
                key=f"scan_station_table_{band}_{active_frequency}",
                column_config={"Miles": st.column_config.NumberColumn(format="%.1f")},
            )
            if event.selection.rows:
                selected = matches.iloc[event.selection.rows[0]].to_dict()
                with st.container(border=True):
                    st.markdown(
                        f"**Selected:** {selected['call']} · {selected['city']}, {selected['region']} · {selected['distance_miles']:.1f} miles"
                    )
                    st.caption("This creates the baseline result and a normal reception log.")
                    if st.button("Confirm station", icon=":material/check_circle:", type="primary"):
                        store.save_bandscan(
                            user_id,
                            str(location["location_id"]),
                            band,
                            active_frequency,
                            "STATION",
                            station_id=str(selected["station_id"]),
                            call=str(selected["call"]),
                        )
                        propagation = "Groundwave" if band == "MW" else "Local"
                        accepted, message = store.append_log(
                            {
                                "user_id": user_id,
                                "location_id": str(location["location_id"]),
                                "station_id": selected["station_id"],
                                "band": band,
                                "frequency": float(selected["frequency"]),
                                "call": selected["call"],
                                "station_city": selected["city"],
                                "station_region": selected["region"],
                                "station_country": selected["country"],
                                "station_county": selected["county"],
                                "station_grid": selected["grid"],
                                "station_latitude": selected["latitude"],
                                "station_longitude": selected["longitude"],
                                "reception_utc": datetime.now(timezone.utc).isoformat(),
                                "distance_miles": selected["distance_miles"],
                                "propagation": propagation,
                                "is_sdr": int(is_sdr),
                                "is_portable": int(is_portable),
                                "notes": "Bandscan baseline",
                                "source": "bandscan",
                            }
                        )
                        if accepted:
                            st.toast(f"{selected['call']} saved to the baseline and logbook")
                        else:
                            st.warning(f"Baseline saved; no second log was created. {message}")
                        st.rerun()
