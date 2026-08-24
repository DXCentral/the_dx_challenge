from __future__ import annotations

import hashlib
from datetime import datetime, time, timezone

import pandas as pd
import streamlit as st
from geopy.geocoders import Nominatim

from app_support import active_challenges_for_band, get_store, require_location
from dxcore.content import station_qualifies_for_challenge
from dxcore.geo import haversine_miles, latlon_to_grid
from dxcore.solar import mw_propagation
from dxcore.stations import FM_FREQUENCIES, MW_10_KHZ, MW_9_KHZ, NWR_FREQUENCIES, stations_on_frequency
from modules.import_console import render_import_console


PROPAGATION = {
    "FM": ["Local", "Tropo", "Meteor Scatter", "Sporadic E", "Aurora", "Aircraft Scatter", "Other"],
    "NWR": ["Local", "Tropo", "Meteor Scatter", "Sporadic E", "Aurora", "Aircraft Scatter", "Other"],
}


def band_frequencies(band: str) -> list[float]:
    if band == "MW":
        return sorted(set(MW_10_KHZ + MW_9_KHZ))
    if band == "FM":
        return FM_FREQUENCIES
    return NWR_FREQUENCIES


def channel_step(band: str, current: float, direction: int) -> float:
    channels = MW_10_KHZ if band == "MW" else band_frequencies(band)
    if band == "MW":
        if direction > 0:
            candidates = [value for value in channels if value > current + 0.01]
            return candidates[0] if candidates else channels[0]
        candidates = [value for value in channels if value < current - 0.01]
        return candidates[-1] if candidates else channels[-1]
    nearest = min(range(len(channels)), key=lambda index: abs(channels[index] - current))
    return channels[(nearest + direction) % len(channels)]


def format_frequency(band: str, value: float) -> str:
    if band == "MW":
        return f"{int(value)} kHz"
    return f"{value:.3f} MHz" if band == "NWR" else f"{value:.1f} MHz"


def manual_station_id(band: str, frequency: float, call: str, city: str, region: str, country: str) -> str:
    raw = f"{band}|{frequency:.3f}|{call}|{city}|{region}|{country}".upper()
    return f"manual_{hashlib.sha1(raw.encode()).hexdigest()[:16]}"


def clear_station_filters(band: str) -> None:
    version_key = f"station_filter_version_{band}"
    st.session_state[version_key] = int(st.session_state.get(version_key, 0)) + 1


st.title("Log entry")
st.caption("Select a station, review the complete reception, then submit. Nothing is logged by a row click alone.")

location = require_location()
store = get_store()
user_id = st.session_state.user["user_id"]

band_options = {"key": "log_band", "persist_state": "session"}
if "log_band" not in st.session_state:
    band_options["default"] = "FM"
band = st.segmented_control("Band", ["MW", "FM", "NWR"], **band_options)
entry_mode = st.segmented_control(
    "Entry method",
    ["Station list", "Manual entry", "Bulk import"],
    default="Station list",
    key="log_entry_method",
)

if entry_mode == "Bulk import":
    render_import_console(location)
    st.stop()

active_sprints = active_challenges_for_band(band)
frequencies = band_frequencies(band)
if active_sprints:
    st.info(
        "Active challenge: "
        + ", ".join(str(challenge["name"]) for challenge in active_sprints)
        + ". Use the optional station-list filter to focus on qualifying targets; normal logging remains fully open.",
        icon=":material/event_available:",
    )
frequency_key = f"log_frequency_{band}"
st.session_state.setdefault(frequency_key, frequencies[0])
if st.session_state[frequency_key] not in frequencies:
    st.session_state[frequency_key] = frequencies[0]

def move_channel(direction: int) -> None:
    st.session_state[frequency_key] = channel_step(band, float(st.session_state[frequency_key]), direction)

with st.container(horizontal=True, vertical_alignment="bottom"):
    st.button("Previous", icon=":material/skip_previous:", on_click=move_channel, args=(-1,))
    frequency = st.selectbox(
        "Frequency",
        options=frequencies,
        key=frequency_key,
        format_func=lambda value: format_frequency(band, value),
        persist_state="session",
        width=260,
    )
    st.button("Next", icon=":material/skip_next:", on_click=move_channel, args=(1,))

selected: dict[str, object] | None = None
source = "station_list"

if entry_mode == "Station list":
    nearby_only = st.toggle(
        "Limit station list to 200 miles",
        value=False,
        key=f"log_nearby_only_{band}",
        help="Leave this off for normal DX logging. Turn it on when you only want nearby targets.",
    )
    challenge_filter = False
    if active_sprints:
        challenge_filter = st.toggle(
            "Active challenge filter",
            value=False,
            key=f"log_challenge_only_{band}",
            help="Show only stations that meet the current challenge's band, frequency, geography, and distance rules. Turn it off at any time to log other DX.",
        )
    matches = stations_on_frequency(
        band,
        frequency,
        float(location["latitude"]),
        float(location["longitude"]),
        radius_miles=200 if nearby_only else None,
    )
    if challenge_filter and not matches.empty:
        matches = matches[
            matches.apply(
                lambda station: any(
                    station_qualifies_for_challenge(station, challenge)
                    for challenge in active_sprints
                ),
                axis=1,
            )
        ].reset_index(drop=True)
    existing = store.logs(user_id)
    heard_ids = set(existing["station_id"]) if not existing.empty else set()
    if matches.empty:
        message = "No stations match this frequency and distance range."
        if challenge_filter:
            message = "No listed stations on this frequency meet the active challenge filter. Turn it off to restore the full list."
        st.info(message + " You can also use Manual entry.")
        st.stop()
    matches = matches.copy()
    station_filter_version = int(st.session_state.get(f"station_filter_version_{band}", 0))
    with st.popover("Filter station list", icon=":material/filter_alt:"):
        filter_columns = st.columns(2)
        call_filter = filter_columns[0].text_input("Call sign / station name", key=f"station_call_{band}_{station_filter_version}")
        city_filter = filter_columns[1].text_input("City", key=f"station_city_{band}_{station_filter_version}")
        filter_columns = st.columns(2)
        region_filter = filter_columns[0].text_input("State / province", key=f"station_region_{band}_{station_filter_version}")
        country_filter = filter_columns[1].text_input("Country", key=f"station_country_{band}_{station_filter_version}")
        filter_columns = st.columns(2)
        county_filter = filter_columns[0].text_input("County / parish", key=f"station_county_{band}_{station_filter_version}")
        grid_filter = filter_columns[1].text_input("Grid", key=f"station_grid_{band}_{station_filter_version}")
        st.button(
            "Clear filters",
            icon=":material/filter_alt_off:",
            on_click=clear_station_filters,
            args=(band,),
            key=f"clear_station_filters_{band}",
        )

    for column, query in [
        ("call", call_filter),
        ("city", city_filter),
        ("region", region_filter),
        ("country", country_filter),
        ("county", county_filter),
        ("grid", grid_filter),
    ]:
        if query.strip():
            matches = matches[matches[column].str.contains(query.strip(), case=False, na=False, regex=False)]
    matches = matches.reset_index(drop=True)
    if matches.empty:
        st.info("No stations match the current filters.")
        st.stop()

    matches["logged"] = matches["station_id"].isin(heard_ids).map({True: "Previously logged", False: "New"})
    view = matches[["call", "city", "region", "country", "county", "grid", "distance_miles", "logged"]].rename(
        columns={
            "call": "Station",
            "city": "City",
            "region": "State / province",
            "country": "Country",
            "county": "County / parish",
            "grid": "Grid",
            "distance_miles": "Miles",
            "logged": "History",
        }
    )
    styled_view = view.style.apply(
        lambda row: [
            "background-color: #BFE8D0; color: #123B26; font-weight: 600"
            if row["History"] == "Previously logged"
            else ""
        ] * len(row),
        axis=1,
    )
    event = st.dataframe(
        styled_view,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=f"log_station_table_{band}_{frequency}",
        column_config={"Miles": st.column_config.NumberColumn(format="%.1f")},
        lazy=False,
    )
    if event.selection.rows:
        selected = matches.iloc[event.selection.rows[0]].to_dict()

elif entry_mode == "Manual entry":
    source = "manual"
    with st.form("manual_station_lookup"):
        call = st.text_input("Call sign / station ID").strip().upper()
        station_city = st.text_input("Station city")
        station_region = st.text_input("Station state / province / region")
        station_country = st.text_input("Station country", value="United States")
        resolve = st.form_submit_button("Resolve station location", icon=":material/location_searching:")
    if resolve:
        query = ", ".join(value.strip() for value in [station_city, station_region, station_country] if value.strip())
        result = Nominatim(user_agent="dx_challenge_s7_station", timeout=8).geocode(query) if query else None
        if not call or result is None:
            st.error("Enter a station ID and a station location that can be resolved.")
        else:
            station_lat = float(result.latitude)
            station_lon = float(result.longitude)
            selected = {
                "station_id": manual_station_id(band, frequency, call, station_city, station_region, station_country),
                "band": band,
                "frequency": frequency,
                "call": call,
                "city": station_city.strip(),
                "region": station_region.strip(),
                "country": station_country.strip(),
                "county": "",
                "grid": latlon_to_grid(station_lat, station_lon),
                "latitude": station_lat,
                "longitude": station_lon,
                "distance_miles": round(
                    haversine_miles(location["latitude"], location["longitude"], station_lat, station_lon), 1
                ),
            }
            st.session_state.manual_station_pending = selected
    selected = st.session_state.get("manual_station_pending")

if selected is None:
    st.caption("Select a station row to open the review form.")
    st.stop()

eligible_sprints = [
    challenge
    for challenge in active_sprints
    if station_qualifies_for_challenge(selected, challenge)
]

with st.container(border=True):
    st.subheader("Review reception")
    st.markdown(
        f"**{selected['call']}** · {format_frequency(band, float(selected['frequency']))} · "
        f"{selected['city']}, {selected['region']}, {selected['country']} · {selected['distance_miles']:.1f} miles"
    )
    if eligible_sprints:
        st.caption(
            "Station criteria match: "
            + ", ".join(str(challenge["name"]) for challenge in eligible_sprints)
            + ". Reception time and propagation are evaluated automatically when challenge results are calculated."
        )
    elif active_sprints:
        st.caption("This reception will still count toward season-long awards and statistics, but not the current challenge.")
    st.session_state.setdefault("log_timing_mode", "Live DX")
    timing = st.segmented_control(
        "Reception timing",
        ["Live DX", "From recording"],
        key="log_timing_mode",
        persist_state="session",
    )
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    with st.form(f"review_log_{selected['station_id']}"):
        if timing == "From recording":
            reception_date = st.date_input(
                "Reception date (UTC)", value=st.session_state.get("last_recording_date", now.date())
            )
            reception_time = st.time_input("Reception time (UTC)", value=time(now.hour, now.minute))
            reception = datetime.combine(reception_date, reception_time, tzinfo=timezone.utc)
        else:
            reception = now
            st.caption(f"Live UTC timestamp: {reception:%Y-%m-%d %H:%M}")

        if band in PROPAGATION:
            propagation = st.selectbox(
                "Propagation mode",
                PROPAGATION[band],
                key=f"log_prop_{band}",
                persist_state="session",
            )
        else:
            propagation = mw_propagation(
                reception, float(location["latitude"]), float(location["longitude"])
            )
            st.text_input("Propagation mode (automatic)", value=propagation, disabled=True)

        st.session_state.setdefault("log_is_sdr", False)
        st.session_state.setdefault("log_is_portable", not bool(location["is_home"]))
        is_sdr = st.checkbox("Received using an SDR", key="log_is_sdr", persist_state="session")
        is_portable = st.checkbox("Portable operation", key="log_is_portable", persist_state="session")
        notes = st.text_area("Programming notes / ID details")
        submitted = st.form_submit_button("Submit reception", icon=":material/send:", type="primary")

    if submitted:
        if timing == "From recording":
            st.session_state.last_recording_date = reception.date()
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
                "reception_utc": reception.isoformat(),
                "distance_miles": selected["distance_miles"],
                "propagation": propagation,
                "is_sdr": int(is_sdr),
                "is_portable": int(is_portable),
                "notes": notes.strip(),
                "source": source,
                "station_review_status": "Pending" if source == "manual" else "",
            }
        )
        if accepted:
            st.success("Reception saved. Band and frequency selections remain in place.")
            st.session_state.pop("manual_station_pending", None)
        else:
            st.error(message, icon=":material/content_copy:")
