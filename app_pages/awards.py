from __future__ import annotations

import math

import pandas as pd
import streamlit as st

from app_support import get_store


AWARDS = {
    "MW · MW Master": {"band": "MW", "field": "station_id", "target": 700, "endorsement": 100, "unit": "unique stations"},
    "MW · Grid Hunter": {"band": "MW", "field": "station_grid", "target": 200, "endorsement": 50, "unit": "unique grids"},
    "MW · County Hunter": {"band": "MW", "field": "station_county", "target": 200, "endorsement": 50, "unit": "unique counties/parishes"},
    "MW · International DXer": {"band": "MW", "field": "station_country", "target": 20, "endorsement": 5, "unit": "unique countries"},
    "MW · Domestic DXer": {"band": "MW", "field": "station_region", "target": 48, "endorsement": None, "unit": "Lower 48 states"},
    "MW · MW Propagation Master": {"band": "MW", "components": {"Daytime": 20, "Sunrise grayline": 150, "Sunset grayline": 150, "Nighttime": 200}},
    "MW · The Gravedigger": {"band": "MW", "field": "station_id", "target": 150, "endorsement": None, "unit": "unique graveyard stations", "graveyard": True},
    "MW · Master Gravedigger": {"band": "MW", "field": "station_id", "target": 200, "endorsement": None, "unit": "unique graveyard stations", "graveyard": True, "long_distance": 10},
    "FM · FM Master": {"band": "FM", "field": "station_id", "target": 1000, "endorsement": 200, "unit": "unique stations"},
    "FM · Grid Hunter": {"band": "FM", "field": "station_grid", "target": 200, "endorsement": 50, "unit": "unique grids"},
    "FM · County Hunter": {"band": "FM", "field": "station_county", "target": 200, "endorsement": 50, "unit": "unique counties/parishes"},
    "FM · Propagation Master": {"band": "FM", "components": {"Tropo": 100, "Meteor Scatter": 100, "Sporadic E": 100}},
    "NWR · NWR Master": {"band": "NWR", "field": "station_id", "target": 100, "endorsement": None, "unit": "unique stations"},
    "NWR · Grid Hunter": {"band": "NWR", "field": "station_grid", "target": 50, "endorsement": 10, "unit": "unique grids"},
    "NWR · County Hunter": {"band": "NWR", "field": "station_county", "target": 50, "endorsement": 10, "unit": "unique counties/parishes"},
    "NWR · WFO Hunter": {"band": "NWR", "field": "wfo", "target": 50, "endorsement": 10, "unit": "unique Weather Forecast Offices"},
    "NWR · Propagation Master": {"band": "NWR", "components": {"Tropo": 5, "Meteor Scatter": 5, "Sporadic E": 5}},
}
GRAVEYARD = {1230.0, 1240.0, 1340.0, 1400.0, 1450.0, 1490.0}
LOWER_48 = {"AL", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY"}


def qualifying_rows(logs: pd.DataFrame, rule: dict[str, object]) -> pd.DataFrame:
    rows = logs[logs["band"] == rule["band"]].copy()
    if rule.get("graveyard"):
        rows = rows[rows["frequency"].astype(float).isin(GRAVEYARD)]
    if rule.get("field") == "station_region":
        rows = rows[rows["station_region"].isin(LOWER_48)]
    return rows


def simple_progress(rows: pd.DataFrame, rule: dict[str, object]) -> pd.DataFrame:
    field = str(rule["field"])
    if field not in rows:
        return pd.DataFrame(columns=["user_id", "count"])
    valid = rows[rows[field].fillna("").astype(str) != ""]
    return valid.groupby("user_id")[field].nunique().reset_index(name="count").sort_values("count", ascending=False)


def component_progress(rows: pd.DataFrame, components: dict[str, int]) -> pd.DataFrame:
    eligible = rows[rows["source"] != "bandscan"].sort_values("reception_utc").drop_duplicates(["user_id", "station_id"])
    pivot = eligible.groupby(["user_id", "propagation"])["station_id"].nunique().unstack(fill_value=0)
    for component in components:
        if component not in pivot:
            pivot[component] = 0
    pivot = pivot[list(components)].reset_index()
    pivot["count"] = pivot[list(components)].sum(axis=1)
    pivot["progress"] = pivot.apply(lambda row: min(row[name] / target for name, target in components.items()), axis=1)
    return pivot.sort_values(["progress", "count"], ascending=False)


st.title("Awards")
st.caption("Choose one Season 7 award. Only that award's calculations and details load.")

logs = get_store().logs()
selected_award = st.selectbox("Award", list(AWARDS), key="selected_award")
my_only = st.toggle("My progress only", value=True)
rule = AWARDS[selected_award]
rows = qualifying_rows(logs, rule) if not logs.empty else pd.DataFrame()

with st.container(border=True):
    st.subheader(selected_award)
    if rule.get("field") == "wfo":
        st.warning("WFO progress is listed in the confirmed rules, but the canonical WFO field is not yet present in the NWR station schema.")
        st.stop()

    if "components" in rule:
        components = rule["components"]
        leaders = component_progress(rows, components) if not rows.empty else pd.DataFrame()
    else:
        leaders = simple_progress(rows, rule) if not rows.empty else pd.DataFrame()
        components = None

    if my_only:
        leaders = leaders[leaders["user_id"] == st.session_state.user["user_id"]] if not leaders.empty else leaders
    else:
        leaders = leaders.head(10)

    if leaders.empty:
        st.progress(0.0, text="No qualifying receptions yet")
    elif not my_only:
        table = leaders.copy()
        table["DXer"] = table["user_id"].map(lambda value: "You" if value == st.session_state.user["user_id"] else value)
        if components:
            table["Progress"] = table["progress"]
            st.dataframe(
                table[["DXer", *components.keys(), "count", "Progress"]],
                hide_index=True,
                column_config={"Progress": st.column_config.ProgressColumn(min_value=0.0, max_value=1.0, format="percent")},
            )
        else:
            target = int(rule["target"])
            table["Progress"] = (table["count"] / target).clip(upper=1)
            st.dataframe(
                table[["DXer", "count", "Progress"]],
                hide_index=True,
                column_config={"Progress": st.column_config.ProgressColumn(min_value=0.0, max_value=1.0, format="percent")},
            )
    else:
        row = leaders.iloc[0]
        if components:
            for name, target in components.items():
                count = int(row[name])
                st.progress(min(count / target, 1.0), text=f"{name}: {count:,} of {target:,} unique stations")
        else:
            count = int(row["count"])
            target = int(rule["target"])
            endorsement = rule.get("endorsement")
            if count < target or not endorsement:
                st.progress(min(count / target, 1.0), text=f"{count:,} of {target:,} {rule['unit']}")
            else:
                next_target = target + math.ceil((count - target + 1) / int(endorsement)) * int(endorsement)
                segment_start = next_target - int(endorsement)
                st.progress((count - segment_start) / int(endorsement), text=f"{count:,} total · {count - segment_start:,} of {endorsement:,} toward {next_target:,}")
            if rule.get("long_distance"):
                user_rows = rows[rows["user_id"] == row["user_id"]].drop_duplicates("station_id")
                long_count = int((user_rows["distance_miles"] >= 800).sum())
                st.progress(min(long_count / int(rule["long_distance"]), 1.0), text=f"{long_count:,} of {rule['long_distance']} stations at 800+ miles")

st.subheader("Counted receptions")
detail_user = st.session_state.user["user_id"]
if not my_only and not leaders.empty:
    detail_options = leaders["user_id"].tolist()
    detail_user = st.selectbox("DXer details", detail_options, format_func=lambda value: "You" if value == st.session_state.user["user_id"] else value)
detail = rows[rows["user_id"] == detail_user].sort_values("reception_utc") if not rows.empty else pd.DataFrame()
if detail.empty:
    st.caption("No counted receptions for this DXer.")
else:
    if components:
        detail = detail[(detail["source"] != "bandscan") & detail["propagation"].isin(components)].drop_duplicates("station_id")
    else:
        detail = detail[detail[str(rule["field"])].fillna("").astype(str) != ""].drop_duplicates(str(rule["field"]))
    st.dataframe(detail[["reception_utc", "call", "frequency", "station_city", "station_region", "station_country", "station_county", "station_grid", "propagation", "distance_miles"]], hide_index=True)
