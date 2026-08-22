from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from app_support import get_store


st.title("My logbook")
st.caption("Only receptions owned by the signed-in DXer are shown or exported. Station-list data is never included.")

store = get_store()
user_id = st.session_state.user["user_id"]
logs = store.logs(user_id)
if logs.empty:
    st.info("No receptions have been submitted in local test mode.")
    st.stop()

bands = st.multiselect("Band", sorted(logs["band"].unique()), default=sorted(logs["band"].unique()))
filtered = logs[logs["band"].isin(bands)].copy()
safe_columns = [
    "reception_utc",
    "band",
    "frequency",
    "call",
    "station_city",
    "station_region",
    "station_country",
    "station_county",
    "station_grid",
    "distance_miles",
    "propagation",
    "is_sdr",
    "is_portable",
    "notes",
    "source",
]
safe = filtered[safe_columns]

with st.container(horizontal=True):
    st.metric("Receptions", f"{len(safe):,}", border=True)
    st.metric("Unique stations", f"{filtered['station_id'].nunique():,}", border=True)
    st.download_button(
        "Export my filtered logs",
        data=safe.to_csv(index=False).encode("utf-8"),
        file_name="my_dx_challenge_logs.csv",
        mime="text/csv",
        icon=":material/download:",
    )

event = st.dataframe(
    safe,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
    key="my_logbook_table",
    column_config={
        "distance_miles": st.column_config.NumberColumn("Miles", format="%.1f"),
        "reception_utc": st.column_config.DatetimeColumn("Reception (UTC)", format="YYYY-MM-DD HH:mm"),
        "is_sdr": st.column_config.CheckboxColumn("SDR"),
        "is_portable": st.column_config.CheckboxColumn("Portable"),
    },
)


@st.dialog("Edit reception", width="large")
def edit_reception_dialog(record: dict[str, object]) -> None:
    st.markdown(f"**{record['call']} · {record['frequency']} {record['band']}**")
    original = pd.to_datetime(record["reception_utc"], utc=True).to_pydatetime()
    with st.form(f"edit_log_{record['log_id']}"):
        reception_date = st.date_input("Reception date (UTC)", value=original.date())
        reception_time = st.time_input("Reception time (UTC)", value=original.time().replace(tzinfo=None))
        propagation = st.text_input("Propagation mode", value=str(record["propagation"]))
        is_sdr = st.checkbox("Received using an SDR", value=bool(record["is_sdr"]))
        is_portable = st.checkbox("Portable operation", value=bool(record["is_portable"]))
        notes = st.text_area("Programming notes / ID details", value=str(record["notes"]))
        submitted = st.form_submit_button("Save changes", icon=":material/save:", type="primary")
    if submitted:
        reception = datetime.combine(reception_date, reception_time, tzinfo=timezone.utc)
        updated, message = store.update_log(
            user_id,
            str(record["log_id"]),
            {
                "reception_utc": reception.isoformat(),
                "propagation": propagation.strip(),
                "is_sdr": int(is_sdr),
                "is_portable": int(is_portable),
                "notes": notes.strip(),
            },
        )
        if updated:
            st.session_state.logbook_notice = message
            st.rerun()
        st.error(message)


@st.dialog("Delete reception")
def delete_reception_dialog(record: dict[str, object]) -> None:
    st.warning(
        f"Delete {record['call']} on {record['frequency']} {record['band']} from "
        f"{pd.to_datetime(record['reception_utc'], utc=True):%Y-%m-%d %H:%M UTC}?"
    )
    st.caption("The stable entry ID is retained as a deleted record so the future Google Sheet sync can update the exact row.")
    if st.button("Delete reception", icon=":material/delete:", type="primary"):
        deleted, message = store.delete_log(user_id, str(record["log_id"]))
        if deleted:
            st.session_state.logbook_notice = message
            st.rerun()
        st.error(message)


if notice := st.session_state.pop("logbook_notice", None):
    st.toast(notice)

if event.selection.rows:
    selected_record = filtered.iloc[event.selection.rows[0]].to_dict()
    st.caption(f"Selected: {selected_record['call']} · entry ID {selected_record['log_id']}")
    with st.container(horizontal=True):
        if st.button("Edit selected reception", icon=":material/edit:"):
            edit_reception_dialog(selected_record)
        if st.button("Delete selected reception", icon=":material/delete:"):
            delete_reception_dialog(selected_record)
else:
    st.caption("Select a row to edit or delete that reception.")
