from __future__ import annotations

import json
import math
import re

import altair as alt
import pandas as pd
try:
    import plotly.graph_objects as go
except ModuleNotFoundError:  # Deployed builds install Plotly from requirements.txt.
    go = None
import pydeck as pdk
import streamlit as st

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
US_NAMES = {"united states", "united states of america", "usa", "us", "u.s.", "u.s.a."}


def _token(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).casefold()).strip("_") or "challenge"


@st.cache_data
def county_assets() -> tuple[pd.DataFrame, dict[str, object]]:
    reference = pd.read_csv(COUNTY_REFERENCE_FILE, dtype=str).fillna("")
    reference["county_key"] = [
        f"{state.upper()}|{normalize_county(county)}"
        for state, county in zip(reference["state"], reference["county"], strict=False)
    ]
    with COUNTY_GEOJSON_FILE.open(encoding="utf-8") as handle:
        return reference, json.load(handle)


def _selection_value(event: object, name: str, field: str) -> str | None:
    try:
        value = event.selection[name]
    except (AttributeError, KeyError, TypeError):
        return None
    if isinstance(value, list) and value:
        return str(value[0].get(field, "")) or None
    if isinstance(value, dict):
        selected = value.get(field)
        if isinstance(selected, list) and selected:
            return str(selected[0])
        if selected:
            return str(selected)
    return None


def _plotly_point(event: object, field: str) -> str | None:
    try:
        points = event.selection.points
    except (AttributeError, KeyError, TypeError):
        return None
    if not points:
        return None
    value = points[0].get(field)
    return str(value) if value not in {None, ""} else None


def _grid_polygon(grid: str) -> tuple[list[list[float]], float, float] | None:
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
        [lon_min, lat_min], [lon_min + 2, lat_min], [lon_min + 2, lat_min + 1],
        [lon_min, lat_min + 1], [lon_min, lat_min],
    ]
    return polygon, lat_min + 0.5, lon_min + 1


def _density_color(value: int, maximum: int) -> list[int]:
    ratio = math.sqrt(value / maximum) if maximum else 0
    return [25, int(95 + 125 * ratio), int(155 + 100 * ratio), int(90 + 145 * ratio)]


def _clear_filters(prefix: str) -> None:
    for field in ["pending_dxer", "pending_region", "pending_country", "pending_grid", "pending_county"]:
        st.session_state.pop(f"{prefix}_{field}", None)
    st.session_state[f"{prefix}_filter_version"] = int(
        st.session_state.get(f"{prefix}_filter_version", 0)
    ) + 1
    st.session_state[f"{prefix}_selection_version"] = int(
        st.session_state.get(f"{prefix}_selection_version", 0)
    ) + 1


def _apply_pending(prefix: str, filter_keys: dict[str, str], valid_values: dict[str, set[str]]) -> None:
    for field in ["dxer", "region", "country", "grid", "county"]:
        pending = st.session_state.pop(f"{prefix}_pending_{field}", None)
        if pending in valid_values[field]:
            st.session_state[filter_keys[field]] = pending


def _select_dxer(event: object, table: pd.DataFrame, prefix: str, current: str) -> None:
    try:
        selected_rows = event.selection.rows
    except (AttributeError, KeyError, TypeError):
        return
    if not selected_rows:
        return
    selected = str(table.iloc[selected_rows[0]]["user_id"])
    if selected and selected != current:
        st.session_state[f"{prefix}_pending_dxer"] = selected
        st.rerun()


def _dxer_table(
    rows: pd.DataFrame,
    name_lookup: dict[str, str],
    *,
    field: str,
    label: str,
    prefix: str,
    current_dxer: str,
) -> None:
    valid = rows[rows[field].fillna("").astype(str).str.strip() != ""]
    table = valid.groupby("user_id")[field].nunique().reset_index(name=label)
    if table.empty:
        st.caption(f"No {label.casefold()} are available for the selected filters.")
        return
    table = table.sort_values(label, ascending=False).reset_index(drop=True)
    maximum = max(int(table[label].max()), 1)
    table["Relative scale"] = table[label] / maximum * 100
    table.insert(0, "DXer", table["user_id"].map(lambda value: name_lookup.get(str(value), "DXer")))
    event = st.dataframe(
        table.drop(columns=["user_id"]),
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=f"{prefix}_{_token(label)}_table",
        column_config={
            "Relative scale": st.column_config.ProgressColumn(
                "Relative scale", min_value=0.0, max_value=100.0, format="%.0f%%"
            )
        },
    )
    st.caption("Select a DXer row to apply that DXer to the counters, map, and reception table.")
    _select_dxer(event, table, prefix, current_dxer)


def _render_filters(
    logs: pd.DataFrame,
    name_lookup: dict[str, str],
    prefix: str,
) -> tuple[pd.DataFrame, str, dict[str, object]]:
    filter_version = int(st.session_state.get(f"{prefix}_filter_version", 0))
    filter_keys = {
        field: f"{prefix}_{field}_{filter_version}"
        for field in ["bands", "propagation", "dxer", "frequency", "region", "country", "grid", "county"]
    }
    regions = sorted(value for value in logs["station_region"].astype(str).unique() if value)
    countries = sorted(value for value in logs["station_country"].astype(str).unique() if value)
    grids = sorted(value for value in logs["grid4"].astype(str).unique() if value)
    dxers = sorted(logs["user_id"].astype(str).unique())
    county_labels = (
        logs[logs["county_key"] != ""]
        .drop_duplicates("county_key")
        .set_index("county_key")
        .apply(lambda row: f"{row['station_county']}, {row['station_region']}", axis=1)
        .to_dict()
    )
    valid_values = {
        "dxer": {"__ALL__", *dxers},
        "region": {"All", *regions},
        "country": {"All", *countries},
        "grid": {"All", *grids},
        "county": {"All", *county_labels},
    }
    _apply_pending(prefix, filter_keys, valid_values)

    with st.container(border=True):
        st.markdown("**Challenge filters**")
        first = st.columns(4)
        all_bands = sorted(logs["band"].astype(str).unique())
        all_propagation = sorted(logs["propagation"].astype(str).unique())
        bands = first[0].multiselect("Band", all_bands, default=all_bands, key=filter_keys["bands"])
        propagation = first[1].multiselect(
            "Propagation", all_propagation, default=all_propagation, key=filter_keys["propagation"]
        )
        dxer_choice = first[2].selectbox(
            "DXer",
            ["__ALL__", *dxers],
            key=filter_keys["dxer"],
            format_func=lambda value: "All DXers" if value == "__ALL__" else name_lookup.get(str(value), "DXer"),
        )
        frequency_options: list[object] = ["All", *sorted(logs["frequency"].astype(float).unique())]
        frequency_choice = first[3].selectbox(
            "Frequency",
            frequency_options,
            key=filter_keys["frequency"],
            format_func=lambda value: "All" if value == "All" else f"{float(value):g}",
        )
        second = st.columns(4)
        region_choice = second[0].selectbox("State / province", ["All", *regions], key=filter_keys["region"])
        country_choice = second[1].selectbox("Country", ["All", *countries], key=filter_keys["country"])
        grid_choice = second[2].selectbox("4-character grid", ["All", *grids], key=filter_keys["grid"])
        county_choice = second[3].selectbox(
            "County / parish",
            ["All", *county_labels],
            key=filter_keys["county"],
            format_func=lambda value: "All" if value == "All" else county_labels.get(value, value),
        )

    st.button(
        "Clear challenge filters",
        icon=":material/filter_alt_off:",
        on_click=_clear_filters,
        args=(prefix,),
        key=f"{prefix}_clear",
    )

    filtered = logs[logs["band"].isin(bands) & logs["propagation"].isin(propagation)].copy()
    if dxer_choice != "__ALL__":
        filtered = filtered[filtered["user_id"].astype(str) == str(dxer_choice)]
    for column, choice in [
        ("frequency", frequency_choice), ("station_region", region_choice),
        ("station_country", country_choice), ("grid4", grid_choice), ("county_key", county_choice),
    ]:
        if choice != "All":
            if column == "frequency":
                filtered = filtered[(filtered[column].astype(float) - float(choice)).abs() < 0.001]
            else:
                filtered = filtered[filtered[column].astype(str) == str(choice)]
    return filtered, str(dxer_choice), {
        "regions": regions,
        "countries": countries,
        "grids": grids,
        "county_labels": county_labels,
        "region_choice": region_choice,
        "country_choice": country_choice,
        "grid_choice": grid_choice,
        "county_choice": county_choice,
    }


def render_challenge_dashboard(
    rows: pd.DataFrame,
    *,
    challenge: dict[str, object],
    name_lookup: dict[str, str],
    store: object,
) -> None:
    if rows.empty:
        st.info("No receptions currently qualify for this challenge.")
        return
    logs = add_geography_keys(rows)
    prefix = f"challenge_{_token(challenge.get('id', challenge.get('name', 'selected')))}"
    filtered, dxer_choice, choices = _render_filters(logs, name_lookup, prefix)
    if filtered.empty:
        st.warning("No qualifying challenge receptions match these filters.")
        return

    unique_logs = filtered.drop_duplicates(["user_id", "station_id"])
    with st.container(horizontal=True):
        st.metric("Receptions", f"{len(filtered):,}", border=True)
        st.metric("Unique stations", f"{unique_logs['station_id'].nunique():,}", border=True)
        st.metric("DXers", f"{unique_logs['user_id'].nunique():,}", border=True)
        st.metric("States / provinces", f"{unique_logs['station_region'].replace('', pd.NA).nunique():,}", border=True)
        st.metric("Countries", f"{unique_logs['station_country'].replace('', pd.NA).nunique():,}", border=True)
        st.metric("4-character grids", f"{unique_logs['grid4'].replace('', pd.NA).nunique():,}", border=True)
        st.metric("Counties / parishes", f"{unique_logs['county_key'].replace('', pd.NA).nunique():,}", border=True)

    analysis = st.selectbox(
        "Challenge analysis",
        [
            "Logs by DXer", "States heard by DXer", "Countries heard by DXer",
            "Grid squares heard by DXer", "Counties heard by DXer", "Station locations", "Paths",
        ],
        key=f"{prefix}_analysis",
    )
    palette = THEMES.get(str(st.session_state.user.get("theme_name")), THEMES["Midnight blue"])
    background = palette["background"]
    surface = palette["surface"]
    text_color = palette["text"]
    empty_fill = "#E2E8F0" if str(st.session_state.user.get("theme_name")) == "Daylight blue" else "#1B2A3A"
    selection_version = int(st.session_state.get(f"{prefix}_selection_version", 0))

    if analysis == "Logs by DXer":
        _dxer_table(
            unique_logs, name_lookup, field="station_id", label="Unique stations",
            prefix=prefix, current_dxer=dxer_choice,
        )
    elif analysis == "States heard by DXer":
        us_rows = unique_logs[
            unique_logs["station_country"].astype(str).str.casefold().isin(US_NAMES)
        ]
        _dxer_table(
            us_rows, name_lookup, field="station_region", label="Unique US states",
            prefix=prefix, current_dxer=dxer_choice,
        )
        counts = us_rows[us_rows["station_region"] != ""].groupby("station_region").size().reset_index(name="Unique logs").rename(columns={"station_region": "region"})
        state_data = pd.DataFrame([{"region": region, "id": fips} for region, fips in STATE_FIPS.items()]).merge(counts, on="region", how="left")
        state_data["Unique logs"] = state_data["Unique logs"].fillna(0).astype(int)
        pick = alt.selection_point(fields=["region"], name="challenge_state_pick", on="click")
        chart = (
            alt.Chart(alt.topo_feature(US_TOPO, "states"))
            .mark_geoshape(stroke=palette["border"], strokeWidth=0.7)
            .transform_lookup(lookup="id", from_=alt.LookupData(state_data, "id", ["region", "Unique logs"]))
            .encode(
                color=alt.condition(
                    "datum['Unique logs'] > 0",
                    alt.Color("Unique logs:Q", scale=alt.Scale(range=["#174A6B", "#168CC4", "#7DE3FF"])),
                    alt.value(empty_fill),
                ),
                tooltip=[alt.Tooltip("region:N", title="State"), alt.Tooltip("Unique logs:Q")],
                opacity=alt.condition(pick, alt.value(1), alt.value(0.88)),
            )
            .project(type="albersUsa").add_params(pick).properties(height=460, background=background)
        )
        event = st.altair_chart(chart, key=f"{prefix}_state_map_{selection_version}", on_select="rerun", selection_mode="challenge_state_pick")
        if picked := _selection_value(event, "challenge_state_pick", "region"):
            if picked != choices["region_choice"]:
                st.session_state[f"{prefix}_pending_region"] = picked
                st.rerun()
    elif analysis == "Countries heard by DXer":
        _dxer_table(
            unique_logs, name_lookup, field="station_country", label="Unique countries",
            prefix=prefix, current_dxer=dxer_choice,
        )
        counts = unique_logs[unique_logs["station_country"] != ""].groupby("station_country").size().reset_index(name="Unique logs").rename(columns={"station_country": "country"})
        if go is None:
            st.info("The interactive country map will appear after the app dependencies finish installing.")
            st.dataframe(counts, hide_index=True)
            return
        fig = go.Figure(go.Choropleth(
            locations=counts["country"], locationmode="country names", z=counts["Unique logs"],
            text=counts["country"], colorscale=[[0.0, "#174A6B"], [0.5, "#168CC4"], [1.0, "#7DE3FF"]],
            marker_line_color=palette["border"], marker_line_width=0.5,
            colorbar_title="Unique logs", hovertemplate="%{text}<br>%{z:,} unique logs<extra></extra>",
        ))
        fig.update_layout(
            template="plotly_white" if str(st.session_state.user.get("theme_name")) == "Daylight blue" else "plotly_dark",
            height=500, margin=dict(l=0, r=0, t=10, b=0), paper_bgcolor=background,
            font_color=text_color, clickmode="event+select", dragmode="pan",
            geo=dict(bgcolor=background, showland=True, landcolor=empty_fill, showocean=True, oceancolor=surface, showcountries=True, countrycolor=palette["border"], projection_type="natural earth"),
        )
        event = st.plotly_chart(
            fig, key=f"{prefix}_country_map_{selection_version}", on_select="rerun", selection_mode="points",
            config={"scrollZoom": True, "displaylogo": False, "toImageButtonOptions": {"format": "jpeg", "filename": f"{prefix}-countries"}},
        )
        if picked := _plotly_point(event, "location"):
            if picked in choices["countries"] and picked != choices["country_choice"]:
                st.session_state[f"{prefix}_pending_country"] = picked
                st.rerun()
    elif analysis == "Grid squares heard by DXer":
        _dxer_table(
            unique_logs, name_lookup, field="grid4", label="Unique 4-character grids",
            prefix=prefix, current_dxer=dxer_choice,
        )
        counts = unique_logs[unique_logs["grid4"] != ""].groupby("grid4").size().reset_index(name="Unique logs")
        maximum = max(int(counts["Unique logs"].max()), 1) if not counts.empty else 1
        grid_rows = []
        for record in counts.to_dict("records"):
            geometry = _grid_polygon(str(record["grid4"]))
            if geometry:
                polygon, latitude, longitude = geometry
                grid_rows.append({**record, "polygon": polygon, "latitude": latitude, "longitude": longitude, "color": _density_color(int(record["Unique logs"]), maximum)})
        if grid_rows:
            event = st.pydeck_chart(
                pdk.Deck(
                    layers=[pdk.Layer("PolygonLayer", id="challenge-grid-density", data=grid_rows, get_polygon="polygon", get_fill_color="color", get_line_color=BAND_COLORS["MW"], line_width_min_pixels=1, pickable=True, auto_highlight=True)],
                    initial_view_state=pdk.ViewState(latitude=sum(row["latitude"] for row in grid_rows) / len(grid_rows), longitude=sum(row["longitude"] for row in grid_rows) / len(grid_rows), zoom=2.2),
                    tooltip={"text": "Grid {grid4}\n{Unique logs} unique logs"}, map_style=None,
                ),
                key=f"{prefix}_grid_map_{selection_version}", on_select="rerun",
            )
            try:
                selected = event.selection.objects.get("challenge-grid-density", [])
            except (AttributeError, KeyError, TypeError):
                selected = []
            if selected:
                picked = str(selected[0].get("grid4", ""))
                if picked in choices["grids"] and picked != choices["grid_choice"]:
                    st.session_state[f"{prefix}_pending_grid"] = picked
                    st.rerun()
    elif analysis == "Counties heard by DXer":
        _dxer_table(
            unique_logs, name_lookup, field="county_key", label="Unique counties / parishes",
            prefix=prefix, current_dxer=dxer_choice,
        )
        reference, geojson = county_assets()
        counts = unique_logs[unique_logs["county_key"] != ""].groupby("county_key").size().reset_index(name="Unique logs")
        count_lookup = dict(zip(counts["county_key"], counts["Unique logs"], strict=False))
        key_lookup = dict(zip(reference["geoid"], reference["county_key"], strict=False))
        maximum = max((int(value) for value in count_lookup.values()), default=1)
        features = []
        for feature in geojson["features"]:
            props = feature.get("properties", {})
            county_key = key_lookup.get(str(props.get("geoid", "")), "")
            count = int(count_lookup.get(county_key, 0))
            features.append({"type": "Feature", "geometry": feature.get("geometry", {}), "properties": {**props, "county_key": county_key, "Unique logs": count, "fill_color": _density_color(count, maximum) if count else [27, 42, 58, 155]}})
        event = st.pydeck_chart(
            pdk.Deck(
                layers=[pdk.Layer("GeoJsonLayer", id="challenge-county-density", data={"type": "FeatureCollection", "features": features}, get_fill_color="properties.fill_color", get_line_color=[92, 130, 160, 130], line_width_min_pixels=0.25, pickable=True, auto_highlight=True)],
                initial_view_state=pdk.ViewState(latitude=38, longitude=-96, zoom=2.6),
                tooltip={"html": "<b>{county_label}</b><br/>{Unique logs} unique logs", "style": {"backgroundColor": surface, "color": text_color}}, map_style=None,
            ),
            key=f"{prefix}_county_map_{selection_version}", on_select="rerun",
        )
        try:
            selected = event.selection.objects.get("challenge-county-density", [])
        except (AttributeError, KeyError, TypeError):
            selected = []
        if selected:
            props = selected[0].get("properties", selected[0])
            match = reference[reference["geoid"] == str(props.get("geoid", ""))]
            if not match.empty:
                county_key = str(match.iloc[0]["county_key"])
                region = str(match.iloc[0]["state"])
                if county_key in choices["county_labels"] and county_key != choices["county_choice"]:
                    st.session_state[f"{prefix}_pending_region"] = region
                    st.session_state[f"{prefix}_pending_county"] = county_key
                    st.rerun()
    else:
        points = unique_logs.dropna(subset=["station_latitude", "station_longitude"]).copy()
        if points.empty:
            st.caption("No station coordinates are available for this view.")
        else:
            grouped = points.groupby(["band", "station_id", "call", "station_city", "station_region", "frequency", "station_latitude", "station_longitude"], as_index=False).size().rename(columns={"size": "log_count"})
            grouped["color"] = grouped["band"].map(BAND_COLORS)
            grouped["radius"] = grouped["log_count"].map(lambda value: 700 + 500 * math.sqrt(value))
            layers: list[pdk.Layer] = []
            if analysis == "Paths":
                location_lookup = store.all_locations().set_index("location_id")
                paths = []
                qths: dict[str, dict[str, object]] = {}
                for record in points.to_dict("records"):
                    if record["location_id"] not in location_lookup.index:
                        continue
                    qth = location_lookup.loc[record["location_id"]]
                    color = BAND_COLORS.get(str(record["band"]), BAND_COLORS["MW"])
                    paths.append({"source": [float(qth["longitude"]), float(qth["latitude"])], "target": [record["station_longitude"], record["station_latitude"]], "color": color, "band": record["band"], "call": record["call"]})
                    qths[str(record["location_id"])] = {"longitude": float(qth["longitude"]), "latitude": float(qth["latitude"]), "label": qth["label"]}
                layers.append(pdk.Layer("ArcLayer", id="challenge-paths", data=paths, get_source_position="source", get_target_position="target", get_source_color="color", get_target_color="color", get_width=1, width_min_pixels=1, width_max_pixels=2, pickable=True))
                layers.append(pdk.Layer("ScatterplotLayer", id="challenge-dxer-locations", data=list(qths.values()), get_position="[longitude, latitude]", get_radius=500, radius_min_pixels=2, radius_max_pixels=3, stroked=True, get_fill_color=[255, 255, 255, 210], get_line_color=[10, 20, 30, 240], line_width_min_pixels=1, pickable=True))
            layers.append(pdk.Layer("ScatterplotLayer", id="challenge-stations", data=grouped, get_position="[station_longitude, station_latitude]", get_radius="radius", radius_min_pixels=2, radius_max_pixels=6, get_fill_color="color", pickable=True, auto_highlight=True))
            st.markdown(":blue-badge[MW · cyan] :green-badge[FM · green] :orange-badge[NWR · orange]")
            st.pydeck_chart(
                pdk.Deck(layers=layers, initial_view_state=pdk.ViewState(latitude=float(grouped["station_latitude"].mean()), longitude=float(grouped["station_longitude"].mean()), zoom=2.5), tooltip={"text": "{call} · {station_city}, {station_region}\n{frequency} · {band}\n{log_count} unique challenge log(s)"}, map_style=None),
                key=f"{prefix}_{_token(analysis)}_map",
            )

    st.subheader("Qualifying reception table")
    table = filtered.copy()
    table.insert(1, "DXer", table["user_id"].map(lambda value: name_lookup.get(str(value), "DXer")))
    sort_fields = {
        "Logs by DXer": ["DXer", "reception_utc"],
        "States heard by DXer": ["station_region", "DXer", "reception_utc"],
        "Countries heard by DXer": ["station_country", "DXer", "reception_utc"],
        "Grid squares heard by DXer": ["grid4", "DXer", "reception_utc"],
        "Counties heard by DXer": ["county_key", "DXer", "reception_utc"],
        "Station locations": ["station_country", "station_region", "call"],
        "Paths": ["DXer", "distance_miles"],
    }
    table = table.sort_values(sort_fields[analysis], ascending=True)
    safe_columns = [
        "reception_utc", "DXer", "band", "frequency", "call", "station_city", "station_region",
        "station_country", "station_county", "station_grid", "distance_miles", "propagation",
        "is_sdr", "is_portable", "notes",
    ]
    st.dataframe(table[safe_columns], hide_index=True, key=f"{prefix}_receptions")
