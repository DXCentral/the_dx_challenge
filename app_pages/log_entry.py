from __future__ import annotations

import hashlib
from datetime import datetime, time, timezone

import pandas as pd
import streamlit as st
from geopy.geocoders import Nominatim

from app_support import bandscan_progress, get_store, require_location
from dxcore.content import active_sprints_for_band, frequency_allowed
from dxcore.geo import haversine_miles, latlon_to_grid
from dxcore.metrics import canonical_daypart
from dxcore.solar import mw_propagation
from dxcore.stations import FM_FREQUENCIES, MW_10_KHZ, MW_9_KHZ, NWR_FREQUENCIES, stations_on_frequency


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


st.title("Log entry")
st.caption("Select a station, review the complete reception, then submit. Nothing is logged by a row click alone.")

location = require_location()
store = get_store()
user_id = st.session_state.user["user_id"]

band_options = {"key": "log_band", "persist_state": "session"}
if "log_band" not in st.session_state:
    band_options["default"] = "FM"
band = st.segmented_control("Band", ["MW", "FM", "NWR"], **band_options)
completed, total, ratio = bandscan_progress(str(location["location_id"]), band)
if ratio < 1:
    st.warning(
        f"{band} logging is locked at this QTH until its bandscan is complete ({completed}/{total}).",
        icon=":material/lock:",
    )
    st.page_link("app_pages/bandscan.py", label="Continue the bandscan", icon=":material/grid_view:")
    st.stop()

active_sprints = active_sprints_for_band(band)
frequencies = band_frequencies(band)
if active_sprints and not any(
    challenge["rules"].get("frequencies", "ALL") == "ALL" for challenge in active_sprints
):
    frequencies = [
        value
        for value in frequencies
        if any(
            frequency_allowed(challenge["rules"].get("frequencies", "ALL"), value)
            for challenge in active_sprints
        )
    ]
if active_sprints:
    st.info(
        "Active challenge restrictions for this band: "
        + ", ".join(str(challenge["name"]) for challenge in active_sprints),
        icon=":material/event_available:",
    )
if not frequencies:
    st.error("The active challenge schedule does not contain a valid frequency for this band.")
    st.stop()
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

entry_mode = st.segmented_control(
    "Entry method", ["Station list", "Manual entry", "Bulk import"], default="Station list", key="log_entry_method"
)

if entry_mode == "Bulk import":
    st.info(
        "The importer review screen is the next build checkpoint. It will not write directly: every row will be classified as Ready, Proposed repair, Ambiguous, Duplicate, or Invalid.",
        icon=":material/upload_file:",
    )
    uploaded = st.file_uploader("Upload a CSV for schema detection", type=["csv"])
    if uploaded is not None:
        preview = pd.read_csv(uploaded, dtype=str, nrows=25).fillna("")
        st.success(f"Read {len(preview.columns)} columns. This preview remains in memory and has not been imported.")
        st.dataframe(preview, hide_index=True)
    st.stop()

selected: dict[str, object] | None = None
source = "station_list"

if entry_mode == "Station list":
    nearby_only = st.toggle(
        "Limit station list to 200 miles",
        value=False,
        key=f"log_nearby_only_{band}",
        help="Leave this off for normal DX logging. Turn it on when you only want nearby targets.",
    )
    matches = stations_on_frequency(
        band,
        frequency,
        float(location["latitude"]),
        float(location["longitude"]),
        radius_miles=200 if nearby_only else None,
    )
    if active_sprints and not matches.empty:
        def country_allowed(country: object) -> bool:
            normalized = str(country).strip().casefold()
            for challenge in active_sprints:
                if not frequency_allowed(
                    challenge["rules"].get("frequencies", "ALL"), float(frequency)
                ):
                    continue
                includes = {
                    str(value).strip().casefold()
                    for value in challenge["rules"].get("include_countries", [])
                }
                excludes = {
                    str(value).strip().casefold()
                    for value in challenge["rules"].get("exclude_countries", [])
                }
                if (not includes or normalized in includes) and normalized not in excludes:
                    return True
            return False

        matches = matches[matches["country"].map(country_allowed)].reset_index(drop=True)
    existing = store.logs(user_id)
    heard_ids = set(existing["station_id"]) if not existing.empty else set()
    if matches.empty:
        st.info("No stations match this frequency and distance range. Expand the range or use Manual entry.")
        st.stop()
    matches = matches.copy()
    with st.popover("Filter station list", icon=":material/filter_alt:"):
        filter_columns = st.columns(2)
        call_filter = filter_columns[0].text_input("Call sign / station name", key=f"station_call_{band}")
        city_filter = filter_columns[1].text_input("City", key=f"station_city_{band}")
        filter_columns = st.columns(2)
        region_filter = filter_columns[0].text_input("State / province", key=f"station_region_{band}")
        country_filter = filter_columns[1].text_input("Country", key=f"station_country_{band}")
        filter_columns = st.columns(2)
        county_filter = filter_columns[0].text_input("County / parish", key=f"station_county_{band}")
        grid_filter = filter_columns[1].text_input("Grid", key=f"station_grid_{band}")

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

if active_sprints:
    station_country = str(selected.get("country", "")).strip().casefold()
    eligible_sprints = []
    for challenge in active_sprints:
        rules = challenge["rules"]
        includes = {str(value).strip().casefold() for value in rules.get("include_countries", [])}
        excludes = {str(value).strip().casefold() for value in rules.get("exclude_countries", [])}
        if (
            frequency_allowed(rules.get("frequencies", "ALL"), float(selected["frequency"]))
            and (not includes or station_country in includes)
            and station_country not in excludes
        ):
            eligible_sprints.append(challenge)
    if not eligible_sprints:
        st.error("This station does not meet the active challenge restrictions for this band.")
        st.stop()
else:
    eligible_sprints = []

with st.container(border=True):
    st.subheader("Review reception")
    st.markdown(
        f"**{selected['call']}** · {format_frequency(band, float(selected['frequency']))} · "
        f"{selected['city']}, {selected['region']}, {selected['country']} · {selected['distance_miles']:.1f} miles"
    )
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
            challenge_modes = sorted(
                {
                    str(mode)
                    for challenge in eligible_sprints
                    for mode in challenge["rules"].get("propagation_modes", [])
                }
            )
            prop_options = [
                value for value in PROPAGATION[band] if not challenge_modes or value in challenge_modes
            ]
            if not prop_options:
                st.error(
                    "The active challenge schedule contains a propagation mode that is not recognized by this entry form."
                )
                st.stop()
            propagation = st.selectbox(
                "Propagation mode",
                prop_options,
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
        allowed_dayparts = {
            str(value)
            for challenge in eligible_sprints
            for value in challenge["rules"].get("dayparts", [])
        }
        allowed_modes = {
            str(value)
            for challenge in eligible_sprints
            for value in challenge["rules"].get("propagation_modes", [])
        }
        if (allowed_dayparts and canonical_daypart(propagation) not in allowed_dayparts) or (
            allowed_modes and propagation not in allowed_modes
        ):
            st.error("This reception's propagation/daypart does not meet the active challenge rules.")
            st.stop()
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
            }
        )
        if accepted:
            st.success("Reception saved. Band and frequency selections remain in place.")
            st.session_state.pop("manual_station_pending", None)
        else:
            st.error(message, icon=":material/content_copy:")
