from __future__ import annotations

import pandas as pd
import streamlit as st

from app_support import challenge_status, display_names, get_store
from dxcore.content import log_qualifies
from modules.challenge_dashboard import render_challenge_dashboard


def challenge_logs(challenge: dict[str, object], logs: pd.DataFrame) -> pd.DataFrame:
    if logs.empty:
        return logs
    mask = logs.apply(lambda row: log_qualifies(row, challenge), axis=1)
    return logs[mask].copy()


def show_results_period(period: str) -> None:
    st.session_state.challenge_results_period = period


st.title("Challenges")
st.caption(
    "Current and completed sprint results use the challenge's saved date, band, frequency, geography, distance, and propagation rules. "
    "Logging remains open outside those rules."
)

store = get_store()
all_logs = store.logs()
name_lookup = display_names()
current, previous, future = challenge_status()
current_sprints = [item for item in current if item["type"] == "sprint"]
previous_sprints = [item for item in previous if item["type"] == "sprint"]
future_sprints = [item for item in future if item["type"] == "sprint"]

st.session_state.setdefault(
    "challenge_results_period", "current" if current_sprints else "previous"
)
if not current_sprints and st.session_state.challenge_results_period == "current":
    st.session_state.challenge_results_period = "previous"
selected_current: dict[str, object] | None = None
selected_previous: dict[str, object] | None = None

st.subheader("Current")
if not current_sprints:
    st.info("No weekly challenge is active. Season-long logging remains open when the season is underway.")
else:
    current_index = 0 if len(current_sprints) == 1 else None
    selected_current = st.selectbox(
        "Current challenge",
        current_sprints,
        index=current_index,
        placeholder="Choose an active challenge",
        format_func=lambda item: item["name"],
        key="current_challenge_results",
        on_change=show_results_period,
        args=("current",),
    )
    if selected_current is None:
        st.caption("More than one challenge is active. Choose one to load its results.")
    else:
        st.button(
            "Show current challenge results",
            icon=":material/query_stats:",
            on_click=show_results_period,
            args=("current",),
        )

st.subheader("Previous")
if not previous_sprints:
    st.caption("No completed Season 7 challenges yet.")
else:
    previous_index = 0 if not current_sprints else None
    selected_previous = st.selectbox(
        "Previous challenge results",
        previous_sprints,
        index=previous_index,
        placeholder="Choose a completed challenge",
        format_func=lambda item: item["name"],
        key="previous_challenge_results",
        on_change=show_results_period,
        args=("previous",),
    )

selected: dict[str, object] | None
selected_period: str
if st.session_state.challenge_results_period == "previous":
    selected = selected_previous
    selected_period = "Previous challenge"
else:
    selected = selected_current
    selected_period = "Current challenge"

if selected is not None:
    with st.container(border=True):
        st.markdown(f"**{selected['name']}**")
        st.caption(
            f"{selected_period} · {selected['start_utc']:%d %b %Y %H%M UTC} – "
            f"{selected['end_utc']:%d %b %Y %H%M UTC}"
        )
        if selected.get("description"):
            st.write(selected["description"])
        if selected_period == "Current challenge":
            st.page_link(
                "app_pages/log_entry.py",
                label="Submit a reception",
                icon=":material/add_circle:",
            )
    render_challenge_dashboard(
        challenge_logs(selected, all_logs),
        challenge=selected,
        name_lookup=name_lookup,
        store=store,
    )

st.subheader("Future")
if not future_sprints:
    st.caption("No future weekly challenges are scheduled yet.")
for challenge in future_sprints:
    with st.container(border=True):
        st.markdown(f"**{challenge['name']}**")
        st.caption(
            f"{challenge['start_utc']:%d %b %Y %H%M UTC} – "
            f"{challenge['end_utc']:%d %b %Y %H%M UTC}"
        )
        st.badge("Preview only", icon=":material/lock_clock:", color="gray")
