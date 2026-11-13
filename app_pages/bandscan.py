from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from app_support import get_store, require_location, season_eligible_logs
from dxcore.bandscan import GRAVEYARD_FREQUENCIES, frequency_statistics, reception_history
from dxcore.presentation import convert_distance, distance_is_km, format_reception
from dxcore.stations import frequencies_for_band
from dxcore.themes import THEMES


COLORS = {
    "local": "#E24A5A",
    "regional": "#F28C28",
    "open": "#39C986",
}
def distance_filters(preferences: dict[str, object]) -> dict[str, str | None]:
    if distance_is_km(preferences):
        return {
            "All": None,
            "Red · within 80 km": "local",
            "Orange · 80–322 km": "regional",
            "Green · beyond 322 km": "open",
        }
    return {
        "All": None,
        "Red · within 50 mi": "local",
        "Orange · 50–200 mi": "regional",
        "Green · beyond 200 mi": "open",
    }


def clear_distance_filter(key: str) -> None:
    st.session_state[key] = "All"


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
logs = season_eligible_logs(get_store().logs(user_id))
preferences = st.session_state.user
distance_filter_options = distance_filters(preferences)

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

if distance_is_km(preferences):
    st.caption(
        ":red-badge[Red · station within 80 km] "
        ":orange-badge[Orange · station within 322 km] "
        ":green-badge[Green · only stations beyond 322 km]"
    )
else:
    st.caption(
        ":red-badge[Red · station within 50 mi] "
        ":orange-badge[Orange · station within 200 mi] "
        ":green-badge[Green · only stations beyond 200 mi]"
    )

filter_key = f"scan_distance_filter_{band}"
st.session_state.setdefault(filter_key, "All")
if st.session_state[filter_key] not in distance_filter_options:
    st.session_state[filter_key] = "All"
with st.container(horizontal=True, vertical_alignment="bottom"):
    distance_filter = st.segmented_control(
        "Filter frequency grid by distance category",
        list(distance_filter_options),
        key=filter_key,
        persist_state="session",
    )
    st.button(
        "Clear distance filter",
        icon=":material/filter_alt_off:",
        disabled=distance_filter == "All",
        key=f"clear_scan_distance_{band}",
        on_click=clear_distance_filter,
        args=(filter_key,),
    )

style_rules: list[str] = []
frequency_keys = {round(value, 3) for value in frequencies}
selected_level = distance_filter_options.get(distance_filter)
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

st.subheader("Frequency stats")
st.caption(
    "Your current-season receptions at the selected QTH, across all logged frequencies "
    f"on {band}. Unique logs count each station once per frequency. "
    "Receptions include repeat catches; maximum distance uses every reception."
)
analysis_options = [
    "Top 10 frequencies by unique logs",
    "Top 10 frequencies by maximum distance",
    "All frequency statistics",
]
if band == "MW":
    analysis_options.insert(1, "Graveyard channels by unique logs")
analysis = st.selectbox(
    "Frequency analysis", analysis_options,
    key=f"scan_frequency_analysis_{band}", persist_state="session",
)
statistics = frequency_statistics(history)
if statistics.empty:
    st.info("Submit receptions from this QTH to build your frequency stats.")
else:
    distance_column = "Max distance (km)" if distance_is_km(preferences) else "Max distance (mi)"
    if analysis == "Graveyard channels by unique logs":
        statistics = statistics.set_index("frequency").reindex(GRAVEYARD_FREQUENCIES).reset_index()
        statistics[["unique_stations", "receptions"]] = (
            statistics[["unique_stations", "receptions"]].fillna(0).astype(int)
        )
        statistics = statistics.sort_values(
            ["unique_stations", "frequency"], ascending=[False, True]
        )
    elif analysis == "Top 10 frequencies by maximum distance":
        statistics = statistics.dropna(subset=["max_distance_miles"]).sort_values(
            ["max_distance_miles", "frequency"], ascending=[False, True]
        ).head(10)
    elif analysis == "Top 10 frequencies by unique logs":
        statistics = statistics.sort_values(
            ["unique_stations", "frequency"], ascending=[False, True]
        ).head(10)
    else:
        statistics = statistics.sort_values("frequency")

    if statistics.empty:
        st.info("No known reception distances are available for this view yet.")
    else:
        view = statistics.rename(columns={
            "unique_stations": "Unique logs", "receptions": "Receptions",
            "farthest_call": "Farthest station", "farthest_location": "Station location",
        }).copy()
        view["Frequency"] = view["frequency"].map(lambda value: frequency_label(band, value))
        view[distance_column] = view["max_distance_miles"].map(
            lambda value: convert_distance(value, preferences)
        )
        view[["Farthest station", "Station location"]] = (
            view[["Farthest station", "Station location"]].fillna("")
        )
        view = view[[
            "Frequency", "Unique logs", "Receptions", distance_column,
            "Farthest station", "Station location",
        ]]
        metric = distance_column if analysis == "Top 10 frequencies by maximum distance" else "Unique logs"
        chart_data = view
        if analysis == "All frequency statistics":
            chart_data = view.sort_values("Unique logs", ascending=False, kind="stable").head(10)
        palette = THEMES.get(str(preferences.get("theme_name")), THEMES["Midnight blue"])
        chart = (
            alt.Chart(chart_data)
            .mark_bar(size=18, cornerRadiusEnd=3, color=palette["primary"])
            .encode(
                x=alt.X(f"{metric}:Q", title=metric),
                y=alt.Y("Frequency:N", sort=chart_data["Frequency"].tolist(), title=None),
                tooltip=[
                    alt.Tooltip("Frequency:N"), alt.Tooltip("Unique logs:Q", format=",d"),
                    alt.Tooltip("Receptions:Q", format=",d"),
                    alt.Tooltip(f"{distance_column}:Q", format=",.1f"),
                    alt.Tooltip("Farthest station:N"), alt.Tooltip("Station location:N"),
                ],
            )
            .properties(height=max(120, len(chart_data) * 28), background=palette["background"])
            .configure_axis(labelColor=palette["text"], titleColor=palette["text"], gridColor=palette["border"])
            .configure_view(strokeWidth=0)
        )
        chart_column, table_column = st.columns([1, 1.5], gap="medium", wrap=True)
        with chart_column:
            st.altair_chart(chart, width="stretch")
        with table_column:
            st.dataframe(
                view, hide_index=True, width="stretch",
                column_config={
                    "Unique logs": st.column_config.ProgressColumn(
                        min_value=0, max_value=max(1, int(view["Unique logs"].max())), format="%d",
                    ),
                    "Receptions": st.column_config.NumberColumn(format="%d"),
                    distance_column: st.column_config.NumberColumn(format="%.1f"),
                },
            )

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
                        when = format_reception(
                            instant if not pd.isna(instant) else reception_row.get("reception_utc", ""),
                            preferences,
                        )
                        propagation = str(reception_row.get("propagation", "")).strip() or "Unspecified"
                        st.markdown(f"- {when} · {propagation}")
