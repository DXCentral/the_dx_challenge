from __future__ import annotations

import math

import pandas as pd
import streamlit as st

from app_support import display_names, get_store, season_eligible_logs, season_marathons
from dxcore.awards import AWARDS, component_progress, qualifying_rows, simple_progress
from dxcore.metrics import canonical_daypart, canonical_propagation


st.title("Awards")
st.caption("Choose one Season 7 award. Only that award's calculations and details load.")

all_logs = get_store().logs()
name_lookup = display_names()
selected_award = st.selectbox("Award", list(AWARDS), key="selected_award")
my_only = st.toggle("My progress only", value=True)
rule = AWARDS[selected_award]
logs = season_eligible_logs(all_logs, str(rule["band"]))
marathons = season_marathons(str(rule["band"]))
if marathons:
    st.caption(
        "Counting only receptions that satisfy: "
        + ", ".join(
            f"{item['name']} ({item['start_utc']:%d %b %Y %H%M UTC} – "
            f"{item['end_utc']:%d %b %Y %H%M UTC})"
            for item in marathons
        )
    )
else:
    st.warning(
        f"No enabled {rule['band']} marathon is configured. This award will remain at zero."
    )
rows = qualifying_rows(logs, rule) if not logs.empty else pd.DataFrame()

with st.container(border=True):
    st.subheader(selected_award)
    if rule.get("field") == "wfo":
        st.warning("WFO progress is listed in the confirmed rules, but the canonical WFO field is not yet present in the NWR station schema.")
        st.stop()

    if "components" in rule:
        components = rule["components"]
        leaders = component_progress(rows, components, str(rule["band"])) if not rows.empty else pd.DataFrame()
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
        table["DXer"] = table["user_id"].map(
            lambda value: "You" if value == st.session_state.user["user_id"] else name_lookup.get(str(value), "DXer")
        )
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
    detail_user = st.selectbox(
        "DXer details",
        detail_options,
        format_func=lambda value: "You"
        if value == st.session_state.user["user_id"]
        else name_lookup.get(str(value), "DXer"),
    )
detail = rows[rows["user_id"] == detail_user].sort_values("reception_utc") if not rows.empty else pd.DataFrame()
if detail.empty:
    st.caption("No counted receptions for this DXer.")
else:
    if components:
        detail = detail[detail["source"] != "bandscan"].copy()
        mapper = canonical_daypart if str(rule["band"]) == "MW" else canonical_propagation
        detail["award_propagation"] = detail["propagation"].map(mapper)
        detail = detail[detail["award_propagation"].isin(components)].drop_duplicates("station_id")
    else:
        detail = detail[detail[str(rule["field"])].fillna("").astype(str) != ""].drop_duplicates(str(rule["field"]))
    st.dataframe(detail[["reception_utc", "call", "frequency", "station_city", "station_region", "station_country", "station_county", "station_grid", "propagation", "distance_miles"]], hide_index=True)
