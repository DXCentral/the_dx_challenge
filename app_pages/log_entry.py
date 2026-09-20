from __future__ import annotations

import hashlib
import html
from datetime import datetime, time, timezone

import pandas as pd
import pydeck as pdk
import streamlit as st
from geopy.geocoders import Nominatim

from app_support import (
    active_challenges_for_band,
    get_station_data,
    get_store,
    require_location,
    season_eligible_logs,
)
from dxcore.content import allowed_challenge_frequencies, station_qualifies_for_challenge
from dxcore.geo import haversine_miles, latlon_to_grid
from dxcore.propagation import FM_NWR_PROPAGATION_OPTIONS, MW_DAYPART_HELP, MW_PROPAGATION_OPTIONS
from dxcore.presentation import (
    convert_distance,
    distance_column_label,
    distance_is_km,
    format_distance,
    format_reception,
)
from dxcore.solar import mw_propagation
from dxcore.station_map import (
    admin1_progress_geojson,
    country_progress_geojson,
    county_progress_geojson,
    grayline_overlay,
    heard_grid_polygons,
    maidenhead_grid_lines,
)
from dxcore.stations import FM_FREQUENCIES, MW_10_KHZ, MW_9_KHZ, NWR_FREQUENCIES, with_distances
from dxcore.subdivisions import north_america_admin1_geojson
from dxcore.themes import THEMES
from modules.import_console import render_import_console


PROPAGATION = {
    "MW": MW_PROPAGATION_OPTIONS,
    "FM": FM_NWR_PROPAGATION_OPTIONS,
    "NWR": FM_NWR_PROPAGATION_OPTIONS,
}


def band_frequencies(band: str) -> list[float]:
    if band == "MW":
        return sorted(set(MW_10_KHZ + MW_9_KHZ))
    if band == "FM":
        return FM_FREQUENCIES
    return NWR_FREQUENCIES


def channel_step(band: str, current: float, direction: int, channels: list[float] | None = None) -> float:
    channels = channels or (MW_10_KHZ if band == "MW" else band_frequencies(band))
    if band == "MW" or channels != band_frequencies(band):
        if direction > 0:
            candidates = [value for value in channels if value > current + 0.001]
            return candidates[0] if candidates else channels[0]
        candidates = [value for value in channels if value < current - 0.001]
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
preferences = st.session_state.user

band_options = {"key": "log_band", "persist_state": "session"}
if "log_band" not in st.session_state:
    band_options["default"] = "FM"
band = st.segmented_control("Band", ["MW", "FM", "NWR"], **band_options)
entry_mode = st.segmented_control(
    "Entry method",
    ["Station list", "Station map", "Manual entry", "Bulk import"],
    default="Station list",
    key="log_entry_method",
)

if entry_mode == "Bulk import":
    render_import_console(location)
    st.stop()

active_sprints = active_challenges_for_band(band)
frequencies = band_frequencies(band)
challenge_filter = False
focused_challenge: dict[str, object] | None = None
if active_sprints:
    st.info(
        "Active challenge: "
        + ", ".join(str(challenge["name"]) for challenge in active_sprints)
        + ". Use the optional station-list filter to focus on qualifying targets; normal logging remains fully open.",
        icon=":material/event_available:",
    )
    if entry_mode in {"Station list", "Station map"}:
        focused_challenge = (
            active_sprints[0]
            if len(active_sprints) == 1
            else st.selectbox(
                "Active challenge target",
                active_sprints,
                format_func=lambda challenge: challenge["name"],
                key=f"log_active_challenge_{band}",
            )
        )
        challenge_filter = st.toggle(
            "Active challenge filter",
            value=False,
            key=f"log_challenge_only_{band}",
            help="When enabled, the frequency and station list move to the selected active challenge. Turn it off at any time to log other DX.",
        )
frequency_key = f"log_frequency_{band}"
challenge_frequencies: list[float] = []
challenge_identity = ""
if challenge_filter and focused_challenge is not None:
    challenge_frequencies = allowed_challenge_frequencies(focused_challenge, frequencies)
    challenge_identity = str(focused_challenge.get("id", focused_challenge.get("name", "")))
frequency_options: list[float | str] = (
    challenge_frequencies
    if challenge_filter and challenge_frequencies
    else (["All", *frequencies] if entry_mode == "Station list" else frequencies)
)
st.session_state.setdefault(frequency_key, frequencies[0])
challenge_focus_key = f"log_challenge_frequency_focus_{band}"
if challenge_filter and challenge_frequencies:
    if st.session_state.get(challenge_focus_key) != challenge_identity:
        st.session_state[frequency_key] = challenge_frequencies[0]
    st.session_state[challenge_focus_key] = challenge_identity
else:
    st.session_state.pop(challenge_focus_key, None)
    if st.session_state[frequency_key] not in frequency_options:
        st.session_state[frequency_key] = frequencies[0]

if challenge_filter and not challenge_frequencies:
    st.warning(
        "The active challenge does not contain a valid frequency for this band. "
        "The full frequency list remains available so normal logging is not blocked."
    )

def move_channel(direction: int) -> None:
    current = st.session_state[frequency_key]
    selectable = [float(value) for value in frequency_options if value != "All"]
    if current == "All":
        st.session_state[frequency_key] = selectable[0 if direction > 0 else -1]
    else:
        restricted_channels = (
            selectable
            if challenge_filter and len(challenge_frequencies) < len(frequencies)
            else None
        )
        st.session_state[frequency_key] = channel_step(
            band, float(current), direction, restricted_channels
        )

with st.container(horizontal=True, vertical_alignment="bottom"):
    st.button(
        "Previous", icon=":material/skip_previous:", on_click=move_channel, args=(-1,),
        disabled=st.session_state[frequency_key] == "All",
    )
    frequency = st.selectbox(
        "Frequency",
        options=frequency_options,
        key=frequency_key,
        format_func=lambda value: "All frequencies" if value == "All" else format_frequency(band, float(value)),
        persist_state="session",
        width=260,
    )
    st.button(
        "Next", icon=":material/skip_next:", on_click=move_channel, args=(1,),
        disabled=frequency == "All",
    )

selected: dict[str, object] | None = None
source = "station_map" if entry_mode == "Station map" else "station_list"

if entry_mode in {"Station list", "Station map"}:
    nearby_only = st.toggle(
        "Limit station list to 322 km" if distance_is_km(preferences) else "Limit station list to 200 miles",
        value=False,
        key=f"log_nearby_only_{band}",
        help="Leave this off for normal DX logging. Turn it on when you only want nearby targets.",
    )
    station_data = get_station_data()
    matches = station_data[station_data["band"].astype(str).str.upper() == band].copy()
    if frequency != "All":
        tolerance = 0.1 if band == "MW" else 0.001
        matches = matches[
            (pd.to_numeric(matches["frequency"], errors="coerce") - float(frequency)).abs()
            < tolerance
        ]
    matches = with_distances(
        matches,
        float(location["latitude"]),
        float(location["longitude"]),
    )
    if nearby_only:
        matches = matches[matches["distance_miles"] <= 200]
    matches = matches.reset_index(drop=True)
    if challenge_filter and not matches.empty:
        matches = matches[
            matches.apply(
                lambda station: station_qualifies_for_challenge(
                    station, focused_challenge
                ) if focused_challenge is not None else any(
                    station_qualifies_for_challenge(station, challenge)
                    for challenge in active_sprints
                ),
                axis=1,
            )
        ].reset_index(drop=True)
    existing = season_eligible_logs(store.logs(user_id))
    heard_ids = set(existing["station_id"]) if not existing.empty else set()
    if matches.empty:
        message = "No stations match this frequency and distance range."
        if challenge_filter:
            message = "No listed stations on this frequency meet the active challenge filter. Turn it off to restore the full list."
        st.info(message + " You can also use Manual entry.")
        st.stop()
    matches = matches.copy()
    station_filter_version = int(st.session_state.get(f"station_filter_version_{band}", 0))
    with st.popover("Filter stations", icon=":material/filter_alt:"):
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

    result_count = len(matches)
    st.caption(f"{result_count:,} station(s) match the current frequency, distance, and search filters.")
    if entry_mode == "Station list":
        table_matches = matches.head(1_000).copy()
        if result_count > len(table_matches):
            st.info(
                f"Showing the nearest {len(table_matches):,} of {result_count:,} matches. "
                "Use the station filters to narrow the full database by call, location, county, or grid."
            )

        table_matches["logged"] = table_matches["station_id"].isin(heard_ids).map({True: "Previously logged", False: "New"})
        distance_label = distance_column_label(preferences)
        view_columns = ["frequency", "call", "city", "region", "country"]
        if band in {"MW", "FM"}:
            view_columns.extend(["format", "network_slogan"])
        if band == "MW":
            view_columns.append("station_notes")
        view_columns.extend(["county", "grid", "logged"])
        view = table_matches[view_columns].copy()
        view[distance_label] = table_matches["distance_miles"].map(
            lambda value: convert_distance(value, preferences)
        )
        ordered_columns = ["frequency", "call", "city", "region", "country"]
        if band in {"MW", "FM"}:
            ordered_columns.extend(["format", "network_slogan"])
        if band == "MW":
            ordered_columns.append("station_notes")
        ordered_columns.extend(["county", "grid", distance_label, "logged"])
        slogan_column_label = "Slogan" if band == "FM" else "Network / slogan"
        view = view[ordered_columns].rename(
            columns={
                "frequency": "Frequency",
                "call": "Station",
                "city": "City",
                "region": "State / province",
                "country": "Country",
                "format": "Format",
                "network_slogan": slogan_column_label,
                "station_notes": "FM //s / notes",
                "county": "County / parish",
                "grid": "Grid",
                "logged": "History",
            }
        )
        if band == "MW":
            st.caption(
                "Format, network/slogan, and FM parallel or identification notes "
                "are provided courtesy of Tim Tromp."
            )
        elif band == "FM":
            st.caption("FM format and slogan information is provided by the WTFDA station data.")
        styled_view = view.style.apply(
            lambda row: [
                "background-color: #BFE8D0; color: #123B26; font-weight: 600"
                if row["History"] == "Previously logged"
                else ""
            ] * len(row),
            axis=1,
        )
        station_column_config = {
            "Frequency": st.column_config.NumberColumn(
                format="%.0f" if band == "MW" else ("%.1f" if band == "FM" else "%.3f")
            ),
            "Station": st.column_config.TextColumn(pinned=True),
            distance_label: st.column_config.NumberColumn(format="%.1f"),
        }
        if band in {"MW", "FM"}:
            station_column_config.update(
                {
                    "Format": st.column_config.TextColumn(width="medium"),
                    slogan_column_label: st.column_config.TextColumn(width="medium"),
                }
            )
        if band == "MW":
            station_column_config["FM //s / notes"] = st.column_config.TextColumn(width="large")
        event = st.dataframe(
            styled_view,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key=f"log_station_table_{band}_{str(frequency).replace('.', '_')}",
            column_config=station_column_config,
            lazy=False,
        )
        if event.selection.rows:
            selected = table_matches.iloc[event.selection.rows[0]].to_dict()
    else:
        map_matches = matches.copy()
        map_matches["latitude"] = pd.to_numeric(map_matches["latitude"], errors="coerce")
        map_matches["longitude"] = pd.to_numeric(map_matches["longitude"], errors="coerce")
        valid_coordinates = (
            map_matches["latitude"].between(-90, 90)
            & map_matches["longitude"].between(-180, 180)
        )
        omitted_count = int((~valid_coordinates).sum())
        map_matches = map_matches[valid_coordinates].reset_index(drop=True)
        if map_matches.empty:
            st.info("None of the matching stations have map coordinates. Use Station list or Manual entry instead.")
            st.stop()
        if omitted_count:
            st.caption(
                f"{omitted_count:,} matching station(s) without valid coordinates are omitted from the map "
                "but remain available in Station list."
            )

        def map_text(value: object) -> str:
            if pd.isna(value) or not str(value).strip():
                return "—"
            return html.escape(str(value).strip())

        map_matches["history_label"] = map_matches["station_id"].isin(heard_ids).map(
            {True: "Previously logged", False: "New / unlogged"}
        )
        map_matches["marker_color"] = map_matches["station_id"].isin(heard_ids).map(
            {True: [0, 190, 230, 235], False: [255, 145, 0, 235]}
        )
        map_matches["frequency_label"] = map_matches["frequency"].map(
            lambda value: format_frequency(band, float(value))
        )
        map_matches["distance_label"] = map_matches["distance_miles"].map(
            lambda value: format_distance(float(value), preferences)
        )
        last_heard = existing.copy()
        if not last_heard.empty:
            last_heard["reception_utc"] = pd.to_datetime(
                last_heard["reception_utc"], utc=True, errors="coerce"
            )
            last_heard_lookup = (
                last_heard.dropna(subset=["reception_utc"])
                .groupby("station_id")["reception_utc"]
                .max()
                .to_dict()
            )
        else:
            last_heard_lookup = {}
        map_matches["last_heard_label"] = map_matches["station_id"].map(
            lambda station_id: format_reception(last_heard_lookup[station_id], preferences)
            if station_id in last_heard_lookup
            else "Unheard"
        )
        map_matches["call_label"] = map_matches["call"].fillna("").astype(str).str.strip()
        for column in [
            "call",
            "city",
            "region",
            "country",
            "county",
            "grid",
            "format",
            "network_slogan",
            "station_notes",
        ]:
            map_matches[column] = map_matches[column].map(map_text)

        points = map_matches[["longitude", "latitude"]].values.tolist()
        map_view = pdk.data_utils.compute_view(points, view_proportion=1)
        map_view.zoom = max(1.0, min(float(map_view.zoom), 7.0))
        tooltip_html = (
            "<b>{call}</b> · {frequency_label}<br/>"
            "{city}, {region}, {country}<br/>"
            "<b>County / parish:</b> {county}<br/>"
            "<b>Grid:</b> {grid}<br/>"
            "<b>Distance:</b> {distance_label}<br/>"
            "<b>Status:</b> {history_label}<br/>"
            "<b>Last heard:</b> {last_heard_label}"
        )
        if band in {"MW", "FM"}:
            tooltip_html += (
                "<br/><b>Format:</b> {format}<br/>"
                + (
                    "<b>Slogan:</b> {network_slogan}"
                    if band == "FM"
                    else "<b>Network / slogan:</b> {network_slogan}"
                )
            )
        if band == "MW":
            tooltip_html += "<br/><b>FM //s / notes:</b> {station_notes}"
            st.caption(
                "MW format, network/slogan, and FM parallel or identification notes "
                "are provided courtesy of Tim Tromp."
            )
        elif band == "FM":
            st.caption("FM format and slogan information is provided by the WTFDA station data.")
        selected_theme = THEMES.get(
            str(preferences.get("theme_name", "Midnight blue")),
            THEMES["Midnight blue"],
        )
        boundary_color = (
            [226, 232, 240, 190]
            if selected_theme["mode"] == "dark"
            else [30, 41, 59, 190]
        )
        overlay_line_color = (
            [203, 213, 225, 105]
            if selected_theme["mode"] == "dark"
            else [51, 65, 85, 105]
        )
        label_color = (
            [248, 250, 252, 245]
            if selected_theme["mode"] == "dark"
            else [15, 23, 42, 245]
        )
        label_outline_color = (
            [15, 23, 42, 255]
            if selected_theme["mode"] == "dark"
            else [248, 250, 252, 255]
        )
        with st.container(horizontal=True, vertical_alignment="bottom"):
            overlay = st.selectbox(
                "Map overlay",
                [
                    "Grayline now",
                    "States / provinces heard",
                    "4-character grids heard",
                    "U.S. counties / parishes heard",
                    "Countries heard",
                    "None",
                ],
                key="station_map_overlay",
                width=320,
            )
            show_call_labels = st.toggle(
                "Show station call labels",
                value=band != "FM",
                key=f"station_map_show_call_labels_{band}",
                help="Labels are off by default for FM because of its much denser station list. Your choice is remembered separately for each band.",
            )
            if overlay == "Grayline now":
                st.button(
                    "Refresh grayline",
                    icon=":material/refresh:",
                    key="refresh_station_map_grayline",
                )

        band_history = existing[
            existing["band"].fillna("").astype(str).str.upper() == band
        ].copy() if not existing.empty else existing.copy()
        map_layers: list[pdk.Layer] = []
        if overlay == "Grayline now":
            grayline_image, terminator_paths, grayline_time = grayline_overlay()
            map_layers.extend(
                [
                    pdk.Layer(
                        "BitmapLayer",
                        id="grayline-shading",
                        image=grayline_image,
                        bounds=[-180, -90, 180, 90],
                        opacity=1,
                        pickable=False,
                    ),
                    pdk.Layer(
                        "PathLayer",
                        id="grayline-terminator",
                        data=terminator_paths,
                        get_path="path",
                        get_color=[255, 184, 77, 235],
                        get_width=2,
                        width_units="pixels",
                        width_min_pixels=1.5,
                        width_max_pixels=3,
                        pickable=False,
                    ),
                ]
            )
            overlay_caption = (
                f"Grayline calculated for {grayline_time:%Y-%m-%d %H:%M UTC}. "
                "The curved amber line marks the solar terminator; the smooth shading transitions through the approximate ±6° twilight zone."
            )
        elif overlay == "States / provinces heard":
            progress_geojson, heard_count = admin1_progress_geojson(band_history)
            map_layers.append(
                pdk.Layer(
                    "GeoJsonLayer",
                    id="admin1-progress",
                    data=progress_geojson,
                    get_fill_color="properties.fill_color",
                    get_line_color=overlay_line_color,
                    line_width_min_pixels=0.5,
                    filled=True,
                    stroked=True,
                    pickable=False,
                )
            )
            overlay_caption = (
                f"{heard_count:,} U.S., Canadian, or Mexican state/province areas heard on {band}. "
                "Cyan fill is heard; low-opacity fill is unheard."
            )
        elif overlay == "4-character grids heard":
            heard_polygons, heard_count = heard_grid_polygons(band_history)
            map_layers.extend(
                [
                    pdk.Layer(
                        "PathLayer",
                        id="grid-boundaries",
                        data=list(maidenhead_grid_lines()),
                        get_path="path",
                        get_color=overlay_line_color,
                        get_width=0.5,
                        width_min_pixels=0.25,
                        width_max_pixels=1,
                        pickable=False,
                    ),
                    pdk.Layer(
                        "PolygonLayer",
                        id="heard-grids",
                        data=heard_polygons,
                        get_polygon="polygon",
                        get_fill_color="color",
                        get_line_color=overlay_line_color,
                        line_width_min_pixels=0.5,
                        filled=True,
                        stroked=True,
                        pickable=False,
                    ),
                ]
            )
            overlay_caption = (
                f"{heard_count:,} unique 4-character grids heard on {band}. "
                "All worldwide grid boundaries are shown; heard grids have a low-opacity cyan fill."
            )
        elif overlay == "U.S. counties / parishes heard":
            progress_geojson, heard_count = county_progress_geojson(band_history)
            map_layers.append(
                pdk.Layer(
                    "GeoJsonLayer",
                    id="county-progress",
                    data=progress_geojson,
                    get_fill_color="properties.fill_color",
                    get_line_color=overlay_line_color,
                    line_width_min_pixels=0.25,
                    filled=True,
                    stroked=True,
                    pickable=False,
                )
            )
            overlay_caption = (
                f"{heard_count:,} U.S. counties or parishes heard on {band}. "
                "Cyan fill is heard; all other county boundaries remain visible."
            )
        elif overlay == "Countries heard":
            progress_geojson, heard_count = country_progress_geojson(band_history)
            map_layers.append(
                pdk.Layer(
                    "GeoJsonLayer",
                    id="country-progress",
                    data=progress_geojson,
                    get_fill_color="properties.fill_color",
                    get_line_color=overlay_line_color,
                    line_width_min_pixels=0.5,
                    filled=True,
                    stroked=True,
                    pickable=False,
                )
            )
            overlay_caption = (
                f"{heard_count:,} mapped countries or territories heard on {band}. "
                "Cyan fill is heard; low-opacity fill is unheard."
            )
        else:
            overlay_caption = "No progress or grayline overlay is selected."

        map_layers.append(
            pdk.Layer(
                "GeoJsonLayer",
                id="admin1-boundaries",
                data=north_america_admin1_geojson(),
                filled=False,
                stroked=True,
                get_line_color=boundary_color,
                line_width_min_pixels=1,
                line_width_max_pixels=2,
                pickable=False,
            )
        )
        map_layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                id="station-markers",
                data=map_matches,
                get_position="[longitude, latitude]",
                get_fill_color="marker_color",
                get_line_color=[15, 23, 42, 230],
                get_radius=12_000,
                radius_min_pixels=5,
                radius_max_pixels=10,
                line_width_min_pixels=1,
                stroked=True,
                filled=True,
                pickable=True,
                auto_highlight=True,
            )
        )
        if show_call_labels:
            map_layers.append(
                pdk.Layer(
                    "TextLayer",
                    id="station-call-labels",
                    data=map_matches,
                    get_position="[longitude, latitude]",
                    get_text="call_label",
                    get_color=label_color,
                    get_size=14_000,
                    size_units="meters",
                    size_min_pixels=8,
                    size_max_pixels=15,
                    get_pixel_offset=[0, -10],
                    get_alignment_baseline="'bottom'",
                    outline_width=3,
                    outline_color=label_outline_color,
                    font_settings={"sdf": True},
                    font_family="Arial Narrow, Arial, sans-serif",
                    billboard=True,
                    pickable=False,
                )
            )
        st.markdown(":orange-badge[New / unlogged] :blue-badge[Previously logged]")
        st.caption(
            "State and province borders are shown for the United States, Canada, and Mexico. "
            + overlay_caption
        )
        st.caption(
            "Hover for station details; click a marker to open the same review form used by Station list."
        )
        map_event = st.pydeck_chart(
            pdk.Deck(
                layers=map_layers,
                initial_view_state=map_view,
                tooltip={"html": tooltip_html},
                map_style=None,
            ),
            height=560,
            on_select="rerun",
            selection_mode="single-object",
            key=f"log_station_map_{band}_{str(frequency).replace('.', '_')}",
        )
        selected_objects = map_event.selection.objects.get("station-markers", [])
        if selected_objects:
            selected_id = str(selected_objects[0].get("station_id", ""))
            selected_rows = matches[matches["station_id"].astype(str) == selected_id]
            if not selected_rows.empty:
                selected = selected_rows.iloc[0].to_dict()

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
    st.caption(
        "Select a station marker to open the review form."
        if entry_mode == "Station map"
        else "Select a station row to open the review form."
    )
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
        f"{selected['city']}, {selected['region']}, {selected['country']} · "
        f"{format_distance(selected['distance_miles'], preferences)}"
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
                "Reception date (UTC)",
                value=st.session_state.get("last_recording_date", now.date()),
                max_value=now.date(),
            )
            reception_time = st.time_input(
                "Reception time (UTC)",
                value=st.session_state.get(
                    "last_recording_time", time(now.hour, now.minute)
                ),
            )
            reception = datetime.combine(reception_date, reception_time, tzinfo=timezone.utc)
        else:
            reception = now
            st.caption(f"Live UTC timestamp: {reception:%Y-%m-%d %H:%M}")

        if band == "MW":
            suggested_propagation = mw_propagation(
                reception, float(location["latitude"]), float(location["longitude"])
            )
            propagation_key = "log_prop_MW"
            if st.session_state.get(propagation_key) not in PROPAGATION["MW"]:
                st.session_state[propagation_key] = suggested_propagation
            propagation = st.selectbox(
                "Propagation mode",
                PROPAGATION["MW"],
                key=propagation_key,
                persist_state="session",
            )
            st.caption(
                f"Suggested from the selected QTH and reception time: {suggested_propagation}. "
                "Change it when the recorded reception used a different propagation/daypart classification."
            )
            st.caption(MW_DAYPART_HELP)
        else:
            propagation = st.selectbox(
                "Propagation mode",
                PROPAGATION[band],
                key=f"log_prop_{band}",
                persist_state="session",
            )

        st.session_state.setdefault("log_is_sdr", False)
        st.session_state.setdefault("log_is_portable", not bool(location["is_home"]))
        is_sdr = st.checkbox("Received using an SDR", key="log_is_sdr", persist_state="session")
        is_portable = st.checkbox("Portable operation", key="log_is_portable", persist_state="session")
        notes = st.text_area("Programming notes / ID details")
        submitted = st.form_submit_button("Submit reception", icon=":material/send:", type="primary")

    if submitted:
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
            if timing == "From recording":
                st.session_state.last_recording_date = reception.date()
                st.session_state.last_recording_time = reception.time().replace(
                    tzinfo=None
                )
            st.success("Reception saved. Band and frequency selections remain in place.")
            st.session_state.pop("manual_station_pending", None)
        else:
            st.error(message, icon=":material/content_copy:")
