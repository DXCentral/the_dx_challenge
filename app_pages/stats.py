from __future__ import annotations

import altair as alt
import pandas as pd
import pydeck as pdk
import streamlit as st

from app_support import get_store


STATE_FIPS = {
    "AL": 1, "AK": 2, "AZ": 4, "AR": 5, "CA": 6, "CO": 8, "CT": 9, "DE": 10,
    "DC": 11, "FL": 12, "GA": 13, "HI": 15, "ID": 16, "IL": 17, "IN": 18,
    "IA": 19, "KS": 20, "KY": 21, "LA": 22, "ME": 23, "MD": 24, "MA": 25,
    "MI": 26, "MN": 27, "MS": 28, "MO": 29, "MT": 30, "NE": 31, "NV": 32,
    "NH": 33, "NJ": 34, "NM": 35, "NY": 36, "NC": 37, "ND": 38, "OH": 39,
    "OK": 40, "OR": 41, "PA": 42, "RI": 44, "SC": 45, "SD": 46, "TN": 47,
    "TX": 48, "UT": 49, "VT": 50, "VA": 51, "WA": 53, "WV": 54, "WI": 55,
    "WY": 56, "PR": 72,
}
US_TOPO = "https://cdn.jsdelivr.net/npm/vega-datasets@v1.29.0/data/us-10m.json"
WORLD_TOPO = "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json"
WORLD_TO_STATION_COUNTRY = {"United States of America": "United States"}


def selection_value(event: object, name: str, field: str) -> str | None:
    try:
        value = event.selection[name]
    except (AttributeError, KeyError, TypeError):
        return None
    if isinstance(value, list) and value:
        return str(value[0].get(field, "")) or None
    if isinstance(value, dict):
        field_value = value.get(field)
        if isinstance(field_value, list) and field_value:
            return str(field_value[0])
        if field_value:
            return str(field_value)
    return None


st.title("Stats")
st.caption("Filters apply to every counter, table, chart, and selected map below. Geography totals use unique stations per DXer.")

store = get_store()
logs = store.logs()
if logs.empty:
    st.info("Submit a staging reception to activate statistics and maps.")
    st.stop()

region_options = ["All"] + sorted(value for value in logs["station_region"].unique() if value)
country_options = ["All"] + sorted(value for value in logs["station_country"].unique() if value)
if pending := st.session_state.pop("stats_pending_region", None):
    if pending in region_options:
        st.session_state.stats_region_choice = pending
if pending := st.session_state.pop("stats_pending_country", None):
    if pending in country_options:
        st.session_state.stats_country_choice = pending

with st.container(border=True):
    st.markdown("**Filters**")
    columns = st.columns(4)
    bands = columns[0].multiselect("Band", sorted(logs["band"].unique()), default=sorted(logs["band"].unique()))
    propagation = columns[1].multiselect("Propagation", sorted(logs["propagation"].unique()), default=sorted(logs["propagation"].unique()))
    dxer_choice = columns[2].selectbox("DXer", ["My logs", "All DXers"])
    frequency_choice = columns[3].selectbox("Frequency", ["All"] + [str(value) for value in sorted(logs["frequency"].unique())])
    columns = st.columns(4)
    region_choice = columns[0].selectbox("State / province", region_options, key="stats_region_choice")
    country_choice = columns[1].selectbox("Country", country_options, key="stats_country_choice")
    grid_choice = columns[2].selectbox("Grid", ["All"] + sorted(value for value in logs["station_grid"].unique() if value))
    county_choice = columns[3].selectbox("County", ["All"] + sorted(value for value in logs["station_county"].unique() if value))

filtered = logs[logs["band"].isin(bands) & logs["propagation"].isin(propagation)].copy()
if dxer_choice == "My logs":
    filtered = filtered[filtered["user_id"] == st.session_state.user["user_id"]]
for column, choice in [
    ("frequency", frequency_choice), ("station_region", region_choice),
    ("station_country", country_choice), ("station_grid", grid_choice),
    ("station_county", county_choice),
]:
    if choice != "All":
        filtered = filtered[filtered[column].astype(str) == choice]

unique_logs = filtered.drop_duplicates(["user_id", "station_id"])
with st.container(horizontal=True):
    st.metric("Receptions", f"{len(filtered):,}", border=True)
    st.metric("Unique stations", f"{filtered['station_id'].nunique():,}", border=True)
    st.metric("US states / provinces", f"{unique_logs['station_region'].replace('', pd.NA).nunique():,}", border=True)
    st.metric("Countries", f"{unique_logs['station_country'].replace('', pd.NA).nunique():,}", border=True)
    st.metric("Grids", f"{unique_logs['station_grid'].replace('', pd.NA).nunique():,}", border=True)
    st.metric("Counties", f"{unique_logs['station_county'].replace('', pd.NA).nunique():,}", border=True)

map_view = st.selectbox("Map / analysis", ["Overview", "Logs by band", "Logs by state / province", "Logs by country", "Station locations", "Paths"])
if filtered.empty:
    st.warning("No logs match these filters.")
elif map_view == "Logs by band":
    band_counts = unique_logs.groupby("band").size().reset_index(name="Unique stations")
    chart = alt.Chart(band_counts).mark_bar(size=34, cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
        x=alt.X("band:N", title=None, sort=["MW", "FM", "NWR"]),
        y=alt.Y("Unique stations:Q", title="Unique stations"),
        color=alt.Color("band:N", legend=None),
        tooltip=["band:N", "Unique stations:Q"],
    ).properties(height=210)
    st.altair_chart(chart)
elif map_view == "Logs by state / province":
    counts = unique_logs[unique_logs["station_region"] != ""].groupby("station_region").size().reset_index(name="Unique stations").rename(columns={"station_region": "region"}).sort_values("Unique stations", ascending=False)
    counts["id"] = counts["region"].map(STATE_FIPS)
    state_map_data = pd.DataFrame(
        [{"region": region, "id": fips} for region, fips in STATE_FIPS.items()]
    ).merge(counts[["region", "Unique stations"]], on="region", how="left")
    state_map_data["Unique stations"] = state_map_data["Unique stations"].fillna(0).astype(int)
    table_col, map_col = st.columns([1, 2])
    with table_col:
        st.dataframe(counts[["region", "Unique stations"]], hide_index=True, height=460)
    with map_col:
        pick = alt.selection_point(fields=["region"], name="state_pick", on="click")
        background = "#0B111A" if st.context.theme.type == "dark" else "#F8FAFC"
        empty_fill = "#1B2A3A" if st.context.theme.type == "dark" else "#E2E8F0"
        chart = alt.Chart(alt.topo_feature(US_TOPO, "states")).mark_geoshape(stroke="#60758E", strokeWidth=0.7).transform_lookup(
            lookup="id", from_=alt.LookupData(state_map_data, "id", ["region", "Unique stations"])
        ).encode(
            color=alt.condition("datum['Unique stations'] > 0", alt.Color("Unique stations:Q", scale=alt.Scale(scheme="blues")), alt.value(empty_fill)),
            tooltip=[alt.Tooltip("region:N", title="State"), alt.Tooltip("Unique stations:Q")],
            opacity=alt.condition(pick, alt.value(1), alt.value(0.88)),
        ).project(type="albersUsa").add_params(pick).properties(height=460, background=background)
        event = st.altair_chart(chart, key="stats_state_map", on_select="rerun", selection_mode="state_pick")
        if picked := selection_value(event, "state_pick", "region"):
            if picked != st.session_state.get("stats_region_choice"):
                st.session_state.stats_pending_region = picked
                st.rerun()
elif map_view == "Logs by country":
    counts = unique_logs[unique_logs["station_country"] != ""].groupby("station_country").size().reset_index(name="Unique stations").rename(columns={"station_country": "country"}).sort_values("Unique stations", ascending=False)
    counts["map_country"] = counts["country"].replace(
        {station: world for world, station in WORLD_TO_STATION_COUNTRY.items()}
    )
    table_col, map_col = st.columns([1, 2])
    with table_col:
        st.dataframe(counts[["country", "Unique stations"]], hide_index=True, height=460)
    with map_col:
        pick = alt.selection_point(fields=["country_name"], name="country_pick", on="click")
        background = "#0B111A" if st.context.theme.type == "dark" else "#F8FAFC"
        empty_fill = "#1B2A3A" if st.context.theme.type == "dark" else "#E2E8F0"
        chart = alt.Chart(alt.topo_feature(WORLD_TOPO, "countries")).mark_geoshape(stroke="#60758E", strokeWidth=0.45).transform_calculate(
            country_name="datum.properties.name"
        ).transform_lookup(
            lookup="country_name", from_=alt.LookupData(counts, "map_country", ["Unique stations"]), default="0"
        ).transform_calculate(
            log_count="toNumber(datum['Unique stations'])"
        ).encode(
            color=alt.condition("datum.log_count > 0", alt.Color("log_count:Q", title="Unique stations", scale=alt.Scale(scheme="blues")), alt.value(empty_fill)),
            tooltip=[alt.Tooltip("country_name:N", title="Country"), alt.Tooltip("log_count:Q", title="Unique stations")],
            opacity=alt.condition(pick, alt.value(1), alt.value(0.88)),
        ).project(type="equalEarth").add_params(pick).properties(height=460, background=background)
        event = st.altair_chart(chart, key="stats_country_map", on_select="rerun", selection_mode="country_pick")
        if picked := selection_value(event, "country_pick", "country_name"):
            picked = WORLD_TO_STATION_COUNTRY.get(picked, picked)
            if picked in country_options and picked != st.session_state.get("stats_country_choice"):
                st.session_state.stats_pending_country = picked
                st.rerun()
elif map_view in {"Station locations", "Paths"}:
    points = unique_logs.dropna(subset=["station_latitude", "station_longitude"]).copy()
    layers = [pdk.Layer("ScatterplotLayer", data=points, get_position="[station_longitude, station_latitude]", get_radius=4200, radius_min_pixels=1, radius_max_pixels=5, get_fill_color=[89, 168, 255, 190], pickable=True)]
    if map_view == "Paths":
        location_lookup = store.locations(st.session_state.user["user_id"]).set_index("location_id")
        path_rows = []
        for row in points.to_dict("records"):
            if row["location_id"] not in location_lookup.index:
                continue
            qth = location_lookup.loc[row["location_id"]]
            path_rows.append({"source": [qth["longitude"], qth["latitude"]], "target": [row["station_longitude"], row["station_latitude"]], "band": row["band"]})
        layers.insert(0, pdk.Layer("ArcLayer", data=path_rows, get_source_position="source", get_target_position="target", get_source_color=[89, 168, 255, 100], get_target_color=[66, 211, 146, 170], get_width=1))
    view = pdk.ViewState(latitude=float(points["station_latitude"].mean()), longitude=float(points["station_longitude"].mean()), zoom=2.5)
    st.pydeck_chart(pdk.Deck(layers=layers, initial_view_state=view, tooltip={"text": "{call} · {station_city}, {station_region}\n{frequency} · {distance_miles} miles"}, map_style=None), key=f"stats_map_{map_view}")
else:
    summary = unique_logs.groupby("band").agg(Receptions=("log_id", "count"), Stations=("station_id", "nunique"))
    st.dataframe(summary)

st.subheader("Filtered reception table")
safe_columns = ["reception_utc", "band", "frequency", "call", "station_city", "station_region", "station_country", "station_county", "station_grid", "distance_miles", "propagation", "is_sdr", "is_portable", "notes"]
st.dataframe(filtered[safe_columns], hide_index=True)
