from __future__ import annotations

import json
import math

import altair as alt
import pandas as pd
import plotly.graph_objects as go
import pydeck as pdk
import streamlit as st

from app_support import display_names, get_store
from dxcore.config import COUNTY_GEOJSON_FILE, COUNTY_REFERENCE_FILE
from dxcore.metrics import add_geography_keys, normalize_county
from dxcore.themes import THEMES


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
BAND_COLORS = {
    "MW": [0, 229, 255, 190],
    "FM": [66, 211, 146, 190],
    "NWR": [247, 166, 72, 205],
}


@st.cache_data
def county_assets() -> tuple[pd.DataFrame, dict[str, object]]:
    reference = pd.read_csv(COUNTY_REFERENCE_FILE, dtype=str).fillna("")
    reference["county_key"] = [
        f"{state.upper()}|{normalize_county(county)}"
        for state, county in zip(reference["state"], reference["county"], strict=False)
    ]
    with COUNTY_GEOJSON_FILE.open(encoding="utf-8") as handle:
        geojson = json.load(handle)
    return reference, geojson


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


def plotly_point(event: object, field: str) -> str | None:
    try:
        points = event.selection.points
    except (AttributeError, KeyError, TypeError):
        return None
    if not points:
        return None
    value = points[0].get(field)
    return str(value) if value not in {None, ""} else None


def grid_polygon(grid: str) -> tuple[list[list[float]], float, float] | None:
    text = str(grid).strip().upper()[:4]
    if len(text) != 4 or not text[:2].isalpha() or not text[2:].isdigit():
        return None
    field_lon = ord(text[0]) - ord("A")
    field_lat = ord(text[1]) - ord("A")
    if not (0 <= field_lon <= 17 and 0 <= field_lat <= 17):
        return None
    lon_min = -180 + field_lon * 20 + int(text[2]) * 2
    lat_min = -90 + field_lat * 10 + int(text[3])
    polygon = [
        [lon_min, lat_min],
        [lon_min + 2, lat_min],
        [lon_min + 2, lat_min + 1],
        [lon_min, lat_min + 1],
        [lon_min, lat_min],
    ]
    return polygon, lat_min + 0.5, lon_min + 1


def density_color(value: int, maximum: int) -> list[int]:
    ratio = math.sqrt(value / maximum) if maximum else 0
    return [25, int(95 + 125 * ratio), int(155 + 100 * ratio), int(90 + 145 * ratio)]


def clear_filters() -> None:
    for key in [
        "stats_pending_region", "stats_pending_country", "stats_pending_grid",
        "stats_pending_county",
    ]:
        st.session_state.pop(key, None)
    # A selected map feature is a stateful frontend input. Remount the map
    # components so that selection cannot immediately reapply a cleared filter.
    st.session_state.stats_map_selection_version = (
        int(st.session_state.get("stats_map_selection_version", 0)) + 1
    )
    st.session_state.stats_filter_version = (
        int(st.session_state.get("stats_filter_version", 0)) + 1
    )


st.title("Stats")
st.caption("Filters apply to every counter, table, chart, and selected map. Award-style geography uses unique canonical stations per DXer.")

store = get_store()
logs = add_geography_keys(store.logs())
if logs.empty:
    st.info("Submit a staging reception to activate statistics and maps.")
    st.stop()

name_lookup = display_names()
user_id = st.session_state.user["user_id"]
selection_version = int(st.session_state.get("stats_map_selection_version", 0))
filter_version = int(st.session_state.get("stats_filter_version", 0))
filter_keys = {
    field: f"stats_{field}_{filter_version}"
    for field in ["bands", "propagation", "dxer", "frequency", "region", "country", "grid", "county"]
}
regions = sorted(value for value in logs["station_region"].unique() if value)
countries = sorted(value for value in logs["station_country"].unique() if value)
grids = sorted(value for value in logs["grid4"].unique() if value)
county_labels = (
    logs[logs["county_key"] != ""]
    .drop_duplicates("county_key")
    .set_index("county_key")
    .apply(lambda row: f"{row['station_county']}, {row['station_region']}", axis=1)
    .to_dict()
)

for pending_key, widget_key, valid in [
    ("stats_pending_region", filter_keys["region"], set(regions)),
    ("stats_pending_country", filter_keys["country"], set(countries)),
    ("stats_pending_grid", filter_keys["grid"], set(grids)),
    ("stats_pending_county", filter_keys["county"], set(county_labels)),
]:
    pending = st.session_state.pop(pending_key, None)
    if pending in valid:
        st.session_state[widget_key] = pending

with st.container(border=True):
    st.markdown("**Filters**")
    first = st.columns(4)
    all_bands = sorted(logs["band"].unique())
    all_propagation = sorted(logs["propagation"].unique())
    bands = first[0].multiselect(
        "Band", all_bands, default=all_bands, key=filter_keys["bands"]
    )
    propagation = first[1].multiselect(
        "Propagation", all_propagation, default=all_propagation, key=filter_keys["propagation"]
    )
    other_dxers = [value for value in sorted(logs["user_id"].unique()) if value != user_id]
    dxer_options = ["__MY__", "__ALL__", *other_dxers]
    dxer_choice = first[2].selectbox(
        "DXer",
        dxer_options,
        key=filter_keys["dxer"],
        format_func=lambda value: {
            "__MY__": "My logs",
            "__ALL__": "All DXers",
        }.get(value, name_lookup.get(str(value), "DXer")),
    )
    frequency_options: list[object] = ["All", *sorted(logs["frequency"].astype(float).unique())]
    frequency_choice = first[3].selectbox(
        "Frequency",
        frequency_options,
        key=filter_keys["frequency"],
        format_func=lambda value: "All" if value == "All" else f"{float(value):g}",
    )
    second = st.columns(4)
    region_choice = second[0].selectbox(
        "State / province", ["All", *regions], key=filter_keys["region"]
    )
    country_choice = second[1].selectbox(
        "Country", ["All", *countries], key=filter_keys["country"]
    )
    grid_choice = second[2].selectbox(
        "4-character grid", ["All", *grids], key=filter_keys["grid"]
    )
    county_choice = second[3].selectbox(
        "County / parish",
        ["All", *county_labels],
        key=filter_keys["county"],
        format_func=lambda value: "All" if value == "All" else county_labels.get(value, value),
    )

st.button(
    "Clear filters",
    icon=":material/filter_alt_off:",
    on_click=clear_filters,
)

filtered = logs[logs["band"].isin(bands) & logs["propagation"].isin(propagation)].copy()
if dxer_choice == "__MY__":
    filtered = filtered[filtered["user_id"] == user_id]
elif dxer_choice != "__ALL__":
    filtered = filtered[filtered["user_id"] == dxer_choice]
for column, choice in [
    ("frequency", frequency_choice),
    ("station_region", region_choice),
    ("station_country", country_choice),
    ("grid4", grid_choice),
    ("county_key", county_choice),
]:
    if choice != "All":
        if column == "frequency":
            filtered = filtered[(filtered[column].astype(float) - float(choice)).abs() < 0.001]
        else:
            filtered = filtered[filtered[column].astype(str) == str(choice)]

unique_logs = filtered.drop_duplicates(["user_id", "station_id"])
with st.container(horizontal=True):
    st.metric("Receptions", f"{len(filtered):,}", border=True)
    st.metric("Unique stations", f"{filtered['station_id'].nunique():,}", border=True)
    st.metric("States / provinces", f"{unique_logs['station_region'].replace('', pd.NA).nunique():,}", border=True)
    st.metric("Countries", f"{unique_logs['station_country'].replace('', pd.NA).nunique():,}", border=True)
    st.metric("4-character grids", f"{unique_logs['grid4'].replace('', pd.NA).nunique():,}", border=True)
    st.metric("Counties / parishes", f"{unique_logs['county_key'].replace('', pd.NA).nunique():,}", border=True)

map_view = st.selectbox(
    "Map / analysis",
    [
        "Overview",
        "Logs by band",
        "Logs by state / province",
        "Logs by country",
        "Logs by grid square",
        "Logs by county",
        "Station locations",
        "Paths",
    ],
    key="stats_map_view",
)

palette = THEMES.get(str(st.session_state.user.get("theme_name")), THEMES["Midnight blue"])
background = palette["background"]
surface = palette["surface"]
text_color = palette["text"]
empty_fill = "#1B2A3A" if str(st.session_state.user.get("theme_name")) != "Daylight blue" else "#E2E8F0"

if filtered.empty:
    st.warning("No logs match these filters.")
elif map_view == "Logs by band":
    band_counts = unique_logs.groupby("band").size().reset_index(name="Unique stations")
    chart = (
        alt.Chart(band_counts)
        .mark_bar(size=28, cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X("band:N", title=None, sort=["MW", "FM", "NWR"]),
            y=alt.Y("Unique stations:Q", title="Unique stations"),
            color=alt.Color("band:N", legend=None),
            tooltip=["band:N", "Unique stations:Q"],
        )
        .properties(height=190, width=560)
    )
    st.altair_chart(chart, width="content")
elif map_view == "Logs by state / province":
    counts = (
        unique_logs[unique_logs["station_region"] != ""]
        .groupby("station_region")
        .size()
        .reset_index(name="Unique stations")
        .rename(columns={"station_region": "region"})
        .sort_values("Unique stations", ascending=False)
    )
    state_map_data = pd.DataFrame(
        [{"region": region, "id": fips} for region, fips in STATE_FIPS.items()]
    ).merge(counts[["region", "Unique stations"]], on="region", how="left")
    state_map_data["Unique stations"] = state_map_data["Unique stations"].fillna(0).astype(int)
    table_col, map_col = st.columns([1, 2])
    with table_col:
        st.dataframe(counts, hide_index=True, height=460)
    with map_col:
        pick = alt.selection_point(fields=["region"], name="state_pick", on="click")
        chart = (
            alt.Chart(alt.topo_feature(US_TOPO, "states"))
            .mark_geoshape(stroke=palette["border"], strokeWidth=0.7)
            .transform_lookup(
                lookup="id",
                from_=alt.LookupData(state_map_data, "id", ["region", "Unique stations"]),
            )
            .encode(
                color=alt.condition(
                    "datum['Unique stations'] > 0",
                    alt.Color(
                        "Unique stations:Q",
                        scale=alt.Scale(range=["#174A6B", "#168CC4", "#7DE3FF"]),
                    ),
                    alt.value(empty_fill),
                ),
                tooltip=[alt.Tooltip("region:N", title="State"), alt.Tooltip("Unique stations:Q")],
                opacity=alt.condition(pick, alt.value(1), alt.value(0.88)),
            )
            .project(type="albersUsa")
            .add_params(pick)
            .properties(height=460, background=background)
        )
        event = st.altair_chart(
            chart,
            key=f"stats_state_map_{selection_version}",
            on_select="rerun",
            selection_mode="state_pick",
        )
        if picked := selection_value(event, "state_pick", "region"):
            if picked != region_choice:
                st.session_state.stats_pending_region = picked
                st.rerun()
elif map_view == "Logs by country":
    counts = (
        unique_logs[unique_logs["station_country"] != ""]
        .groupby("station_country")
        .size()
        .reset_index(name="Unique stations")
        .rename(columns={"station_country": "country"})
        .sort_values("Unique stations", ascending=False)
    )
    table_col, map_col = st.columns([1, 2])
    with table_col:
        st.dataframe(counts, hide_index=True, height=500)
    with map_col:
        fig = go.Figure(
            go.Choropleth(
                locations=counts["country"],
                locationmode="country names",
                z=counts["Unique stations"],
                text=counts["country"],
                colorscale=[
                    [0.0, "#174A6B"],
                    [0.5, "#168CC4"],
                    [1.0, "#7DE3FF"],
                ],
                zmin=0,
                marker_line_color=palette["border"],
                marker_line_width=0.5,
                colorbar_title="Unique stations",
                hovertemplate="%{text}<br>%{z:,} unique stations<extra></extra>",
            )
        )
        fig.update_layout(
            template="plotly_white" if str(st.session_state.user.get("theme_name")) == "Daylight blue" else "plotly_dark",
            height=500,
            margin=dict(l=0, r=0, t=10, b=0),
            paper_bgcolor=background,
            font_color=text_color,
            clickmode="event+select",
            dragmode="pan",
            geo=dict(
                bgcolor=background,
                showland=True,
                landcolor=empty_fill,
                showocean=True,
                oceancolor=surface,
                showcountries=True,
                countrycolor=palette["border"],
                projection_type="natural earth",
            ),
        )
        event = st.plotly_chart(
            fig,
            key=f"stats_country_plotly_{selection_version}",
            on_select="rerun",
            selection_mode="points",
            config={
                "scrollZoom": True,
                "displaylogo": False,
                "toImageButtonOptions": {"format": "jpeg", "filename": "dx-challenge-logs-by-country"},
            },
        )
        if picked := plotly_point(event, "location"):
            if picked in countries and picked != country_choice:
                st.session_state.stats_pending_country = picked
                st.rerun()
elif map_view == "Logs by grid square":
    counts = (
        unique_logs[unique_logs["grid4"] != ""]
        .groupby("grid4")
        .size()
        .reset_index(name="Unique stations")
        .sort_values("Unique stations", ascending=False)
    )
    maximum = int(counts["Unique stations"].max()) if not counts.empty else 1
    grid_rows = []
    for row in counts.to_dict("records"):
        geometry = grid_polygon(str(row["grid4"]))
        if geometry:
            polygon, latitude, longitude = geometry
            grid_rows.append(
                {
                    **row,
                    "polygon": polygon,
                    "latitude": latitude,
                    "longitude": longitude,
                    "color": density_color(int(row["Unique stations"]), maximum),
                }
            )
    table_col, map_col = st.columns([1, 2])
    with table_col:
        st.dataframe(counts, hide_index=True, height=500)
    with map_col:
        event = st.pydeck_chart(
            pdk.Deck(
                layers=[
                    pdk.Layer(
                        "PolygonLayer",
                        id="grid-density",
                        data=grid_rows,
                        get_polygon="polygon",
                        get_fill_color="color",
                        get_line_color=BAND_COLORS["MW"],
                        line_width_min_pixels=1,
                        pickable=True,
                        auto_highlight=True,
                    )
                ],
                initial_view_state=pdk.ViewState(
                    latitude=sum(row["latitude"] for row in grid_rows) / len(grid_rows),
                    longitude=sum(row["longitude"] for row in grid_rows) / len(grid_rows),
                    zoom=2.2,
                ),
                tooltip={"text": "Grid {grid4}\n{Unique stations} unique stations"},
                map_style=None,
            ),
            key=f"stats_grid_map_{selection_version}",
            on_select="rerun",
        )
        try:
            selected = event.selection.objects.get("grid-density", [])
        except (AttributeError, KeyError, TypeError):
            selected = []
        if selected:
            picked = str(selected[0].get("grid4", ""))
            if picked in grids and picked != grid_choice:
                st.session_state.stats_pending_grid = picked
                st.rerun()
elif map_view == "Logs by county":
    reference, county_geojson = county_assets()
    counts = (
        unique_logs[unique_logs["county_key"] != ""]
        .groupby(["county_key", "station_region", "station_county"])
        .size()
        .reset_index(name="Unique stations")
        .sort_values("Unique stations", ascending=False)
    )
    table_col, map_col = st.columns([1, 2])
    with table_col:
        st.dataframe(
            counts[["station_county", "station_region", "Unique stations"]].rename(
                columns={"station_county": "County / parish", "station_region": "State"}
            ),
            hide_index=True,
            height=500,
        )
    with map_col:
        count_lookup = dict(zip(counts["county_key"], counts["Unique stations"], strict=False))
        key_lookup = dict(zip(reference["geoid"], reference["county_key"], strict=False))
        maximum_count = max((int(value) for value in count_lookup.values()), default=1)
        county_features = []
        for feature in county_geojson["features"]:
            properties = feature.get("properties", {})
            geoid = str(properties.get("geoid", ""))
            county_key = key_lookup.get(geoid, "")
            station_count = int(count_lookup.get(county_key, 0))
            county_features.append(
                {
                    "type": "Feature",
                    "geometry": feature.get("geometry", {}),
                    "properties": {
                        **properties,
                        "county_key": county_key,
                        "Unique stations": station_count,
                        "fill_color": density_color(station_count, maximum_count)
                        if station_count
                        else [27, 42, 58, 155],
                    },
                }
            )
        event = st.pydeck_chart(
            pdk.Deck(
                layers=[
                    pdk.Layer(
                        "GeoJsonLayer",
                        id="county-density",
                        data={"type": "FeatureCollection", "features": county_features},
                        get_fill_color="properties.fill_color",
                        get_line_color=[92, 130, 160, 130],
                        line_width_min_pixels=0.25,
                        pickable=True,
                        auto_highlight=True,
                    )
                ],
                initial_view_state=pdk.ViewState(latitude=38, longitude=-96, zoom=2.6),
                tooltip={
                    "html": "<b>{county_label}</b><br/>{Unique stations} unique stations",
                    "style": {"backgroundColor": surface, "color": text_color},
                },
                map_style=None,
            ),
            key=f"stats_county_map_{selection_version}",
            on_select="rerun",
        )
        try:
            selected = event.selection.objects.get("county-density", [])
        except (AttributeError, KeyError, TypeError):
            selected = []
        if selected:
            picked = selected[0]
            properties = picked.get("properties", picked)
            geoid = str(properties.get("geoid", ""))
            match = reference[reference["geoid"] == geoid]
            if not match.empty:
                county_key = str(match.iloc[0]["county_key"])
                region = str(match.iloc[0]["state"])
                already_applied = (
                    county_key == county_choice and region == region_choice
                )
                if county_key in county_labels and not already_applied:
                    st.session_state.stats_pending_region = region
                    st.session_state.stats_pending_county = county_key
                    st.rerun()
elif map_view in {"Station locations", "Paths"}:
    points = unique_logs.dropna(subset=["station_latitude", "station_longitude"]).copy()
    grouped = (
        points.groupby(
            ["band", "station_id", "call", "station_city", "station_region", "frequency", "station_latitude", "station_longitude"],
            as_index=False,
        )
        .size()
        .rename(columns={"size": "log_count"})
    )
    grouped["color"] = grouped["band"].map(BAND_COLORS)
    grouped["radius"] = grouped["log_count"].map(lambda value: 700 + 500 * math.sqrt(value))
    layers: list[pdk.Layer] = []
    if map_view == "Paths":
        location_lookup = store.all_locations().set_index("location_id")
        path_rows = []
        qth_rows: dict[str, dict[str, object]] = {}
        for row in points.to_dict("records"):
            if row["location_id"] not in location_lookup.index:
                continue
            qth = location_lookup.loc[row["location_id"]]
            color = BAND_COLORS.get(str(row["band"]), BAND_COLORS["MW"])
            path_rows.append(
                {
                    "source": [float(qth["longitude"]), float(qth["latitude"])],
                    "target": [row["station_longitude"], row["station_latitude"]],
                    "color": color,
                    "band": row["band"],
                    "call": row["call"],
                }
            )
            qth_rows[str(row["location_id"])] = {
                "longitude": float(qth["longitude"]),
                "latitude": float(qth["latitude"]),
                "label": qth["label"],
            }
        layers.append(
            pdk.Layer(
                "ArcLayer",
                id="reception-paths",
                data=path_rows,
                get_source_position="source",
                get_target_position="target",
                get_source_color="color",
                get_target_color="color",
                get_width=1,
                width_min_pixels=1,
                width_max_pixels=2,
                pickable=True,
            )
        )
        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                id="dxer-locations",
                data=list(qth_rows.values()),
                get_position="[longitude, latitude]",
                get_radius=500,
                radius_min_pixels=2,
                radius_max_pixels=3,
                stroked=True,
                get_fill_color=[255, 255, 255, 210],
                get_line_color=[10, 20, 30, 240],
                line_width_min_pixels=1,
                pickable=True,
            )
        )
    layers.append(
        pdk.Layer(
            "ScatterplotLayer",
            id="station-locations",
            data=grouped,
            get_position="[station_longitude, station_latitude]",
            get_radius="radius",
            radius_min_pixels=2,
            radius_max_pixels=6,
            get_fill_color="color",
            pickable=True,
            auto_highlight=True,
        )
    )
    st.markdown(":blue-badge[MW · cyan] :green-badge[FM · green] :orange-badge[NWR · orange]")
    view = pdk.ViewState(
        latitude=float(grouped["station_latitude"].mean()),
        longitude=float(grouped["station_longitude"].mean()),
        zoom=2.5,
    )
    st.pydeck_chart(
        pdk.Deck(
            layers=layers,
            initial_view_state=view,
            tooltip={
                "text": "{call} · {station_city}, {station_region}\n{frequency} · {band}\n{log_count} unique filtered log(s)"
            },
            map_style=None,
        ),
        key=f"stats_map_{map_view}",
    )
else:
    summary = unique_logs.groupby("band").agg(
        Receptions=("log_id", "count"), Stations=("station_id", "nunique")
    )
    st.dataframe(summary)

st.subheader("Filtered reception table")
safe_columns = [
    "reception_utc", "band", "frequency", "call", "station_city", "station_region",
    "station_country", "station_county", "station_grid", "distance_miles", "propagation",
    "is_sdr", "is_portable", "notes",
]
st.dataframe(filtered[safe_columns], hide_index=True, key="stats_filtered_receptions")
