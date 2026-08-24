from __future__ import annotations

import altair as alt
import pandas as pd
import pydeck as pdk
import streamlit as st

from app_support import challenge_status, display_names, get_store
from dxcore.content import log_qualifies
from dxcore.metrics import add_geography_keys, challenge_scores


def challenge_logs(challenge: dict[str, object]) -> pd.DataFrame:
    logs = get_store().logs()
    if logs.empty:
        return logs
    mask = logs.apply(lambda row: log_qualifies(row, challenge), axis=1)
    return add_geography_keys(logs[mask].copy())


st.title("Challenges")
current, previous, future = challenge_status()
name_lookup = display_names()

st.subheader("Current")
current_sprints = [item for item in current if item["type"] == "sprint"]
if not current_sprints:
    st.info("No weekly challenge is active. Season-long logging remains open when the season is underway.")
else:
    challenge = st.selectbox("Current challenge", current_sprints, format_func=lambda item: item["name"])
    with st.container(border=True):
        st.markdown(f"**{challenge['name']}**")
        st.caption(f"{challenge['start_utc']:%d %b %Y %H%M UTC} – {challenge['end_utc']:%d %b %Y %H%M UTC}")
        st.page_link("app_pages/log_entry.py", label="Submit a reception", icon=":material/add_circle:")
        view = st.selectbox("Challenge view", ["Leaderboard", "Map", "Chart", "Reception table"])
        rows = challenge_logs(challenge)
        unique = rows.drop_duplicates(["user_id", "station_id"]) if not rows.empty else rows
        if rows.empty:
            st.caption("No qualifying challenge receptions yet.")
        elif view == "Leaderboard":
            leaders = unique.groupby("user_id").agg(Unique_stations=("station_id", "nunique"), States=("station_region", "nunique"), Countries=("station_country", "nunique"), Grids=("grid4", lambda values: values[values != ""].nunique()), Counties=("county_key", lambda values: values[values != ""].nunique())).reset_index()
            scores = challenge_scores(rows, str(challenge.get("scoring_method", "Unique stations")))
            leaders = leaders.merge(scores, on="user_id", how="left").sort_values("score", ascending=False)
            leaders.insert(0, "DXer", leaders["user_id"].map(lambda value: name_lookup.get(str(value), "DXer")))
            leaders = leaders.rename(columns={"score": str(challenge.get("scoring_method", "Score"))})
            st.dataframe(leaders.drop(columns=["user_id"]), hide_index=True)
        elif view == "Map":
            points = unique.dropna(subset=["station_latitude", "station_longitude"])
            st.pydeck_chart(pdk.Deck(layers=[pdk.Layer("ScatterplotLayer", data=points, get_position="[station_longitude, station_latitude]", get_radius=4200, radius_min_pixels=1, radius_max_pixels=5, get_fill_color=[89, 168, 255, 190], pickable=True)], initial_view_state=pdk.ViewState(latitude=float(points["station_latitude"].mean()), longitude=float(points["station_longitude"].mean()), zoom=2.5), tooltip={"text": "{call} · {station_city}, {station_region}"}, map_style=None))
        elif view == "Chart":
            score_label = str(challenge.get("scoring_method", "Unique stations"))
            chart_data = challenge_scores(rows, score_label).head(10).rename(columns={"score": score_label})
            chart_data["DXer"] = chart_data["user_id"].map(lambda value: name_lookup.get(str(value), "DXer"))
            chart = alt.Chart(chart_data).mark_bar(size=24).encode(
                x=alt.X(field=score_label, type="quantitative"),
                y=alt.Y("DXer:N", sort="-x"),
                tooltip=["DXer", score_label],
            ).properties(height=300)
            st.altair_chart(chart)
        else:
            table = rows[["reception_utc", "user_id", "band", "frequency", "call", "station_city", "station_region", "station_country", "station_grid", "distance_miles", "propagation"]].copy()
            table.insert(1, "DXer", table["user_id"].map(lambda value: name_lookup.get(str(value), "DXer")))
            st.dataframe(table.drop(columns=["user_id"]), hide_index=True)

st.subheader("Previous")
if not previous:
    st.caption("No completed Season 7 challenges yet.")
for challenge in previous:
    with st.container(border=True):
        st.markdown(f"**{challenge['name']}**")
        st.caption(f"Ended {challenge['end_utc']:%d %b %Y %H%M UTC}")
        st.page_link("app_pages/leaderboards.py", label="Open filtered results", icon=":material/leaderboard:")

st.subheader("Future")
future_sprints = [item for item in future if item["type"] == "sprint"]
if not future_sprints:
    st.caption("No future weekly challenges are scheduled yet.")
for challenge in future_sprints:
    with st.container(border=True):
        st.markdown(f"**{challenge['name']}**")
        st.caption(f"{challenge['start_utc']:%d %b %Y %H%M UTC} – {challenge['end_utc']:%d %b %Y %H%M UTC}")
        st.badge("Preview only", icon=":material/lock_clock:", color="gray")
