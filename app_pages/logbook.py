from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from app_support import get_store
from dxcore.metrics import add_geography_keys
from dxcore.propagation import FM_NWR_PROPAGATION_OPTIONS, MW_PROPAGATION_OPTIONS


def clear_logbook_filters() -> None:
    st.session_state.logbook_filter_version = (
        int(st.session_state.get("logbook_filter_version", 0)) + 1
    )


st.title("My logbook")
st.caption("Only receptions owned by the signed-in DXer are shown or exported. Station-list data is never included.")

store = get_store()
user_id = st.session_state.user["user_id"]
logs = store.logs(user_id)
if logs.empty:
    st.info("No receptions have been submitted in local test mode.")
    st.stop()

logs = add_geography_keys(logs)
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
filter_version = int(st.session_state.get("logbook_filter_version", 0))
filter_keys = {
    field: f"logbook_{field}_{filter_version}"
    for field in ["bands", "propagation", "frequency", "source", "region", "country", "grid", "county"]
}

with st.container(border=True):
    st.markdown("**Filters**")
    st.caption("DXer scope is fixed to My logs on this page.")
    first = st.columns(4)
    all_bands = sorted(logs["band"].astype(str).unique())
    all_propagation = sorted(logs["propagation"].astype(str).unique())
    bands = first[0].multiselect(
        "Band", all_bands, default=all_bands, key=filter_keys["bands"]
    )
    propagation = first[1].multiselect(
        "Propagation",
        all_propagation,
        default=all_propagation,
        key=filter_keys["propagation"],
    )
    frequency_choice = first[2].selectbox(
        "Frequency",
        ["All", *sorted(logs["frequency"].astype(float).unique())],
        key=filter_keys["frequency"],
        format_func=lambda value: "All" if value == "All" else f"{float(value):g}",
    )
    source_choice = first[3].selectbox(
        "Source",
        ["All", *sorted(logs["source"].astype(str).unique())],
        key=filter_keys["source"],
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
    on_click=clear_logbook_filters,
)

filtered = logs[
    logs["band"].isin(bands) & logs["propagation"].isin(propagation)
].copy()
for column, choice in [
    ("frequency", frequency_choice),
    ("source", source_choice),
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

if filtered.empty:
    st.warning("No receptions match these filters.")

action_slot = st.container()
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
        propagation_options = (
            MW_PROPAGATION_OPTIONS
            if str(record["band"]).upper() == "MW"
            else FM_NWR_PROPAGATION_OPTIONS
        )
        current_propagation = str(record["propagation"])
        if current_propagation not in propagation_options:
            propagation_options = [current_propagation, *propagation_options]
        propagation = st.selectbox(
            "Propagation / MW daypart",
            propagation_options,
            index=propagation_options.index(current_propagation),
        )
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
                "propagation": propagation,
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

with action_slot:
    if event.selection.rows:
        selected_record = filtered.iloc[event.selection.rows[0]].to_dict()
        st.caption(f"Selected: {selected_record['call']} · entry ID {selected_record['log_id']}")
        with st.container(horizontal=True):
            if st.button("Edit selected reception", icon=":material/edit:"):
                edit_reception_dialog(selected_record)
            if st.button("Delete selected reception", icon=":material/delete:"):
                delete_reception_dialog(selected_record)
    else:
        st.caption("Select a row below to activate the edit and delete controls.")
