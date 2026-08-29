from __future__ import annotations

import pandas as pd
import streamlit as st

from app_support import challenge_status, display_names, get_store
from dxcore.content import log_qualifies
from dxcore.metrics import add_geography_keys, canonical_daypart


def clear_filters(prefix: str) -> None:
    key = f"{prefix}_filter_version"
    st.session_state[key] = int(st.session_state.get(key, 0)) + 1


def filter_logs(
    logs: pd.DataFrame,
    name_lookup: dict[str, str],
    *,
    prefix: str,
    sprint_names: list[str] | None = None,
) -> pd.DataFrame:
    version = int(st.session_state.get(f"{prefix}_filter_version", 0))
    key = lambda field: f"{prefix}_{field}_{version}"
    regions = sorted(value for value in logs["station_region"].astype(str).unique() if value)
    countries = sorted(value for value in logs["station_country"].astype(str).unique() if value)
    grids = sorted(value for value in logs["grid4"].astype(str).unique() if value)
    county_labels = (
        logs[logs["county_key"] != ""]
        .drop_duplicates("county_key")
        .set_index("county_key")
        .apply(lambda row: f"{row['station_county']}, {row['station_region']}", axis=1)
        .to_dict()
    )
    dxers = sorted(logs["user_id"].astype(str).unique())
    frequencies: list[object] = ["All", *sorted(logs["frequency"].astype(float).unique())]
    dayparts = ["All", "Daytime", "Sunrise grayline", "Sunset grayline", "Nighttime"]

    with st.container(border=True):
        st.markdown("**Leaderboard filters**")
        first = st.columns(4)
        all_bands = sorted(logs["band"].astype(str).unique())
        all_propagation = sorted(logs["propagation"].astype(str).unique())
        bands = first[0].multiselect("Band", all_bands, default=all_bands, key=key("bands"))
        propagation = first[1].multiselect(
            "Propagation", all_propagation, default=all_propagation, key=key("propagation")
        )
        dxer = first[2].selectbox(
            "DXer", ["__ALL__", *dxers], key=key("dxer"),
            format_func=lambda value: "All DXers" if value == "__ALL__" else name_lookup.get(str(value), "DXer"),
        )
        frequency = first[3].selectbox(
            "Frequency", frequencies, key=key("frequency"),
            format_func=lambda value: "All" if value == "All" else f"{float(value):g}",
        )
        second = st.columns(4)
        region = second[0].selectbox("State / province", ["All", *regions], key=key("region"))
        country = second[1].selectbox("Country", ["All", *countries], key=key("country"))
        grid = second[2].selectbox("4-character grid", ["All", *grids], key=key("grid"))
        county = second[3].selectbox(
            "County / parish", ["All", *county_labels], key=key("county"),
            format_func=lambda value: "All" if value == "All" else county_labels.get(value, value),
        )
        third = st.columns(4)
        daypart = third[0].selectbox(
            "MW propagation / daypart", dayparts, key=key("daypart"),
            help="Selecting a daypart limits the table to MW receptions in that daypart.",
        )
        sprint = "All"
        if sprint_names is not None:
            sprint = third[1].selectbox("Sprint name", ["All", *sprint_names], key=key("sprint"))

    st.button(
        "Clear leaderboard filters", icon=":material/filter_alt_off:",
        on_click=clear_filters, args=(prefix,), key=f"{prefix}_clear",
    )

    filtered = logs[logs["band"].isin(bands) & logs["propagation"].isin(propagation)].copy()
    if dxer != "__ALL__":
        filtered = filtered[filtered["user_id"].astype(str) == str(dxer)]
    for column, choice in [
        ("frequency", frequency), ("station_region", region), ("station_country", country),
        ("grid4", grid), ("county_key", county),
    ]:
        if choice != "All":
            if column == "frequency":
                filtered = filtered[(filtered[column].astype(float) - float(choice)).abs() < 0.001]
            else:
                filtered = filtered[filtered[column].astype(str) == str(choice)]
    if daypart != "All":
        filtered = filtered[(filtered["band"] == "MW") & (filtered["mw_daypart"] == daypart)]
    if sprint_names is not None and sprint != "All":
        filtered = filtered[filtered["sprint_name"] == sprint]
    return filtered


def standings(logs: pd.DataFrame, name_lookup: dict[str, str]) -> pd.DataFrame:
    if logs.empty:
        return pd.DataFrame()
    table = (
        logs.groupby("user_id")
        .agg(
            unique_stations=("station_id", "nunique"),
            receptions=("log_id", "count"),
            states_provinces=("station_region", lambda values: values[values != ""].nunique()),
            countries=("station_country", lambda values: values[values != ""].nunique()),
            grids=("grid4", lambda values: values[values != ""].nunique()),
            counties=("county_key", lambda values: values[values != ""].nunique()),
        )
        .sort_values(["unique_stations", "receptions"], ascending=False)
        .reset_index()
    )
    table.insert(0, "rank", range(1, len(table) + 1))
    table.insert(1, "DXer", table["user_id"].map(lambda value: name_lookup.get(str(value), "DXer")))
    return table.drop(columns=["user_id"])


st.title("Leaderboards")
st.caption(
    "Season leaders summarize the season-long marathons. Sprint leaders summarize only receptions that qualify for current or completed sprint challenges. "
    "Select any column heading to sort the displayed table."
)

logs = add_geography_keys(get_store().logs())
if logs.empty:
    st.info("No staging receptions are available for standings.")
    st.stop()
logs["mw_daypart"] = logs["propagation"].map(canonical_daypart)
name_lookup = display_names()

st.subheader("Season leaders")
season_filtered = filter_logs(logs, name_lookup, prefix="season_leaders")
season_table = standings(season_filtered, name_lookup)
if season_table.empty:
    st.caption("No season receptions match these filters.")
else:
    st.dataframe(season_table, hide_index=True, key="season_leaderboard")

st.subheader("Sprint challenge leaders")
current, previous, _ = challenge_status()
sprints = [item for item in current + previous if item["type"] == "sprint"]
qualified_frames: list[pd.DataFrame] = []
for challenge in sprints:
    mask = logs.apply(lambda row: log_qualifies(row, challenge), axis=1)
    matches = logs[mask].copy()
    if not matches.empty:
        matches["sprint_name"] = str(challenge["name"])
        matches["sprint_id"] = str(challenge["id"])
        qualified_frames.append(matches)

if not qualified_frames:
    st.caption("No receptions qualify for a current or completed sprint challenge yet.")
else:
    sprint_logs = pd.concat(qualified_frames, ignore_index=True)
    sprint_names = [str(item["name"]) for item in sprints]
    sprint_filtered = filter_logs(
        sprint_logs, name_lookup, prefix="sprint_leaders", sprint_names=sprint_names
    )
    sprint_table = standings(sprint_filtered, name_lookup)
    if sprint_table.empty:
        st.caption("No sprint receptions match these filters.")
    else:
        st.dataframe(sprint_table, hide_index=True, key="sprint_leaderboard")
