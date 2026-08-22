import pandas as pd
import streamlit as st

from app_support import challenge_status, get_store


st.title("Leaderboards")
st.caption("Staging standings use unique canonical stations. The complete Summer of DX scoring matrix is the next rules-engine integration.")

logs = get_store().logs()
current, previous, future = challenge_status()
challenge_options = [item["name"] for item in current + previous + future if item["type"] == "sprint"]
selected_challenge = st.selectbox("Challenge results", challenge_options or ["No weekly challenge configured"])

if logs.empty:
    st.info("No staging receptions are available for standings.")
    st.stop()

leaders = (
    logs.groupby("user_id")
    .agg(
        unique_stations=("station_id", "nunique"),
        receptions=("log_id", "count"),
        states_provinces=("station_region", "nunique"),
        countries=("station_country", "nunique"),
        grids=("station_grid", "nunique"),
        counties=("station_county", lambda values: values[values != ""].nunique()),
    )
    .sort_values(["unique_stations", "receptions"], ascending=False)
    .reset_index()
)
leaders.insert(0, "rank", range(1, len(leaders) + 1))
st.dataframe(leaders, hide_index=True)

st.subheader("Challenge coverage")
st.caption("Possible-station percentages will activate when the selected challenge’s eligible station universe is resolved.")

