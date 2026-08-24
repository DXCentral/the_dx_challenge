import pandas as pd
import streamlit as st

from app_support import challenge_status, display_names, get_store
from dxcore.content import log_qualifies
from dxcore.metrics import add_geography_keys, challenge_scores


st.title("Leaderboards")
st.caption(
    "Season standings use unique canonical geography and station totals. Challenge standings include only receptions that meet that challenge's saved criteria."
)

logs = add_geography_keys(get_store().logs())
name_lookup = display_names()
current, previous, future = challenge_status()

if logs.empty:
    st.info("No staging receptions are available for standings.")
    st.stop()

st.subheader("Season leaders")
leaders = (
    logs.groupby("user_id")
    .agg(
        unique_stations=("station_id", "nunique"),
        receptions=("log_id", "count"),
        states_provinces=("station_region", "nunique"),
        countries=("station_country", "nunique"),
        grids=("grid4", lambda values: values[values != ""].nunique()),
        counties=("county_key", lambda values: values[values != ""].nunique()),
    )
    .sort_values(["unique_stations", "receptions"], ascending=False)
    .reset_index()
)
leaders.insert(0, "rank", range(1, len(leaders) + 1))
leaders.insert(
    1,
    "DXer",
    leaders["user_id"].map(lambda value: name_lookup.get(str(value), "DXer")),
)
st.dataframe(leaders.drop(columns=["user_id"]), hide_index=True)

st.subheader("Challenge results")
challenges = [item for item in current + previous + future if item["type"] == "sprint"]
if not challenges:
    st.caption("No weekly challenges are configured.")
    st.stop()

selected = st.selectbox(
    "Challenge",
    challenges,
    format_func=lambda item: item["name"],
)
qualified = logs[logs.apply(lambda row: log_qualifies(row, selected), axis=1)].copy()
if qualified.empty:
    st.caption("No receptions currently qualify for this challenge.")
    st.stop()

method = str(selected.get("scoring_method", "Unique stations"))
scores = challenge_scores(qualified, method)
coverage = (
    qualified.groupby("user_id")
    .agg(
        receptions=("log_id", "count"),
        unique_stations=("station_id", "nunique"),
        states_provinces=("station_region", "nunique"),
        countries=("station_country", "nunique"),
        grids=("grid4", lambda values: values[values != ""].nunique()),
        counties=("county_key", lambda values: values[values != ""].nunique()),
    )
    .reset_index()
)
results = scores.merge(coverage, on="user_id", how="left")
results.insert(0, "rank", range(1, len(results) + 1))
results.insert(
    1,
    "DXer",
    results["user_id"].map(lambda value: name_lookup.get(str(value), "DXer")),
)
results = results.rename(columns={"score": method})
st.caption(
    f"Scoring: {method} · {selected['start_utc']:%d %b %Y %H%M UTC}–{selected['end_utc']:%d %b %Y %H%M UTC}"
)
st.dataframe(results.drop(columns=["user_id"]), hide_index=True)
