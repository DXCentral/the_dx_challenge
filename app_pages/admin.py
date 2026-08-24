from __future__ import annotations

from datetime import date, datetime, time, timezone

import pandas as pd
import streamlit as st

from app_support import display_names, get_store, require_admin_access
from dxcore.content import parse_frequency_spec


def as_datetime(value: object, fallback: datetime) -> datetime:
    parsed = pd.to_datetime(value, utc=True, errors="coerce")
    return fallback if pd.isna(parsed) else parsed.to_pydatetime()


def utc_value(day: date, clock: time) -> str:
    return datetime.combine(day, clock, tzinfo=timezone.utc).replace(second=0, microsecond=0).isoformat()


def as_bool(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


@st.dialog("Confirm deletion")
def confirm_delete(kind: str, record_id: str, label: str) -> None:
    st.warning(f"Delete {kind.lower()} **{label}**? This cannot be undone.")
    if st.button("Delete permanently", icon=":material/delete:", type="primary"):
        if kind == "Announcement":
            deleted, message = get_store().delete_announcement(record_id)
        else:
            deleted, message = get_store().delete_challenge(record_id)
        if deleted:
            st.session_state.admin_notice = message
            st.rerun()
        st.error(message)


require_admin_access()
store = get_store()

st.title("Administration")
st.caption(
    "Manage public content, challenge criteria, support tickets, and unlisted-station review. Every save is mirrored to the private Google Sheet when durable sync is active."
)
if notice := st.session_state.pop("admin_notice", None):
    st.toast(notice)
if st.button("Lock admin portal", icon=":material/lock:"):
    st.session_state.admin_authorized = False
    st.session_state.pop("admin_authorized_email", None)
    st.rerun()

section = st.selectbox(
    "Administration area",
    ["Announcements", "Challenges", "Support tickets", "Station review queue"],
)

if section == "Announcements":
    st.subheader("Announcements")
    announcements = store.announcements()
    records = {str(row["announcement_id"]): row for row in announcements.to_dict("records")}
    options = ["__new__", *records]
    selected_id = st.selectbox(
        "Announcement to edit",
        options,
        format_func=lambda value: "Add new announcement"
        if value == "__new__"
        else str(records[value]["title"]),
    )
    record = records.get(selected_id, {})
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start = as_datetime(record.get("start_utc"), now)
    end_value = str(record.get("end_utc", "")).strip()
    end = as_datetime(end_value, now.replace(hour=23, minute=59))
    with st.form(f"admin_announcement_{selected_id}"):
        title = st.text_input("Title", value=str(record.get("title", "")), max_chars=160)
        body = st.text_area("Announcement", value=str(record.get("body", "")), height=160)
        start_columns = st.columns(2)
        start_date = start_columns[0].date_input("Start date (UTC)", value=start.date())
        start_time = start_columns[1].time_input("Start time (UTC)", value=start.time())
        no_end = st.checkbox("No expiration", value=not bool(end_value))
        end_columns = st.columns(2)
        end_date = end_columns[0].date_input("End date (UTC)", value=end.date(), disabled=no_end)
        end_time = end_columns[1].time_input("End time (UTC)", value=end.time(), disabled=no_end)
        active = st.toggle("Visible when within its date window", value=as_bool(record.get("active", 1)))
        save = st.form_submit_button("Save announcement", icon=":material/save:", type="primary")
    if save:
        try:
            announcement_id = store.upsert_announcement(
                {
                    "announcement_id": "" if selected_id == "__new__" else selected_id,
                    "title": title,
                    "body": body,
                    "start_utc": utc_value(start_date, start_time),
                    "end_utc": "" if no_end else utc_value(end_date, end_time),
                    "active": active,
                }
            )
            st.session_state.admin_notice = f"Announcement {announcement_id} saved."
            st.rerun()
        except ValueError as error:
            st.error(str(error))
    if selected_id != "__new__" and st.button(
        "Delete announcement", icon=":material/delete:"
    ):
        confirm_delete("Announcement", selected_id, str(record.get("title", selected_id)))
    if not announcements.empty:
        st.dataframe(
            announcements[["title", "start_utc", "end_utc", "active", "updated_utc"]],
            hide_index=True,
        )

elif section == "Challenges":
    st.subheader("Challenges")
    challenges = store.challenges()
    records = {str(row["challenge_id"]): row for row in challenges.to_dict("records")}
    options = ["__new__", *records]
    selected_id = st.selectbox(
        "Challenge to edit",
        options,
        format_func=lambda value: "Add new challenge"
        if value == "__new__"
        else str(records[value]["challenge_name"]),
    )
    record = records.get(selected_id, {})
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    start = as_datetime(record.get("start_utc"), now)
    end = as_datetime(record.get("end_utc"), now.replace(hour=23, minute=59))
    band_defaults = [
        value for value in str(record.get("bands", "MW")).split("|") if value in {"MW", "FM", "NWR"}
    ] or ["MW"]
    propagation_options = [
        "Local", "Groundwave", "Skywave", "Tropo", "Meteor Scatter", "Sporadic E",
        "Aurora", "Aircraft Scatter", "Other",
    ]
    propagation_defaults = [
        value for value in str(record.get("propagation_modes", "")).split("|") if value in propagation_options
    ]
    daypart_options = ["Daytime", "Sunrise grayline", "Sunset grayline", "Nighttime"]
    daypart_defaults = [
        value for value in str(record.get("dayparts", "")).split("|") if value in daypart_options
    ]
    with st.form(f"admin_challenge_{selected_id}"):
        name = st.text_input("Challenge name", value=str(record.get("challenge_name", "")), max_chars=160)
        challenge_type = st.segmented_control(
            "Challenge type",
            ["sprint", "marathon"],
            default=str(record.get("challenge_type", "sprint")) or "sprint",
        )
        timeframe_tag = st.text_input(
            "Timeframe label", value=str(record.get("timeframe_tag", "")), placeholder="Week 1 · 910 kHz"
        )
        date_columns = st.columns(4)
        start_date = date_columns[0].date_input("Start date (UTC)", value=start.date())
        start_time = date_columns[1].time_input("Start time (UTC)", value=start.time())
        end_date = date_columns[2].date_input("End date (UTC)", value=end.date())
        end_time = date_columns[3].time_input("End time (UTC)", value=end.time())
        bands = st.multiselect("Bands", ["MW", "FM", "NWR"], default=band_defaults)
        frequencies = st.text_input(
            "Frequencies",
            value=str(record.get("frequencies", "ALL")) or "ALL",
            help="Use ALL, a single value (910), a pipe-separated list (910|1180), ranges (88.1-92.5), or a mixture.",
        )
        geography = st.columns(2)
        include_countries = geography[0].text_input(
            "Only these countries", value=str(record.get("include_countries", "")), help="Separate values with |"
        )
        exclude_countries = geography[1].text_input(
            "Exclude these countries", value=str(record.get("exclude_countries", "")), help="Separate values with |"
        )
        geography = st.columns(2)
        include_regions = geography[0].text_input(
            "Only these states / provinces", value=str(record.get("include_regions", "")), help="Use abbreviations separated with |"
        )
        exclude_regions = geography[1].text_input(
            "Exclude these states / provinces", value=str(record.get("exclude_regions", "")), help="Use abbreviations separated with |"
        )
        distance_columns = st.columns(2)
        min_distance = distance_columns[0].text_input(
            "Minimum distance (miles)", value=str(record.get("min_distance", ""))
        )
        max_distance = distance_columns[1].text_input(
            "Maximum distance (miles)", value=str(record.get("max_distance", ""))
        )
        propagation_modes = st.multiselect(
            "Propagation modes", propagation_options, default=propagation_defaults
        )
        dayparts = st.multiselect("MW dayparts", daypart_options, default=daypart_defaults)
        scoring_method = st.selectbox(
            "Leaderboard scoring",
            [
                "Unique stations", "Unique states/provinces", "Unique countries",
                "Unique 4-character grids", "Unique counties/parishes", "Total receptions",
            ],
            index=max(
                0,
                [
                    "Unique stations", "Unique states/provinces", "Unique countries",
                    "Unique 4-character grids", "Unique counties/parishes", "Total receptions",
                ].index(str(record.get("scoring_method", "Unique stations")))
                if str(record.get("scoring_method", "Unique stations")) in [
                    "Unique stations", "Unique states/provinces", "Unique countries",
                    "Unique 4-character grids", "Unique counties/parishes", "Total receptions",
                ]
                else 0,
            ),
        )
        description = st.text_area("Public description", value=str(record.get("description", "")))
        active = st.toggle("Challenge is enabled", value=as_bool(record.get("active", 1)))
        save = st.form_submit_button("Save challenge", icon=":material/save:", type="primary")
    if save:
        try:
            if not bands:
                raise ValueError("Choose at least one band.")
            parse_frequency_spec(frequencies)
            for label, value in (("Minimum distance", min_distance), ("Maximum distance", max_distance)):
                if value.strip() and float(value) < 0:
                    raise ValueError(f"{label} cannot be negative.")
            challenge_id = store.upsert_challenge(
                {
                    "challenge_id": "" if selected_id == "__new__" else selected_id,
                    "challenge_type": challenge_type,
                    "challenge_name": name,
                    "timeframe_tag": timeframe_tag or name,
                    "start_utc": utc_value(start_date, start_time),
                    "end_utc": utc_value(end_date, end_time),
                    "bands": "|".join(bands),
                    "frequencies": frequencies.strip().upper(),
                    "include_countries": include_countries.strip(),
                    "exclude_countries": exclude_countries.strip(),
                    "include_regions": include_regions.strip().upper(),
                    "exclude_regions": exclude_regions.strip().upper(),
                    "propagation_modes": "|".join(propagation_modes),
                    "dayparts": "|".join(dayparts),
                    "min_distance": min_distance.strip(),
                    "max_distance": max_distance.strip(),
                    "scoring_method": scoring_method,
                    "description": description,
                    "active": active,
                }
            )
            st.session_state.admin_notice = f"Challenge {challenge_id} saved."
            st.rerun()
        except (TypeError, ValueError) as error:
            st.error(str(error))
    if selected_id != "__new__" and st.button(
        "Delete challenge", icon=":material/delete:"
    ):
        confirm_delete("Challenge", selected_id, str(record.get("challenge_name", selected_id)))
    if not challenges.empty:
        st.dataframe(
            challenges[
                ["challenge_name", "challenge_type", "start_utc", "end_utc", "bands", "frequencies", "scoring_method", "active"]
            ],
            hide_index=True,
        )

elif section == "Support tickets":
    st.subheader("Support tickets")
    tickets = store.support_tickets()
    if tickets.empty:
        st.caption("No support or feature-request tickets have been submitted.")
    else:
        names = display_names()
        tickets = tickets.copy()
        tickets["DXer"] = tickets["user_id"].map(lambda value: names.get(str(value), "DXer"))
        show_closed = st.toggle("Include resolved and closed tickets")
        visible = tickets if show_closed else tickets[~tickets["status"].isin(["Resolved", "Closed"])]
        st.dataframe(
            visible[["ticket_id", "DXer", "category", "subject", "created_utc", "updated_utc", "status", "admin_comment"]],
            hide_index=True,
        )
        if not visible.empty:
            ids = visible["ticket_id"].astype(str).tolist()
            selected_id = st.selectbox(
                "Ticket to respond to",
                ids,
                format_func=lambda value: f"{value} · {visible[visible['ticket_id'] == value].iloc[0]['subject']}",
            )
            ticket = visible[visible["ticket_id"] == selected_id].iloc[0]
            with st.container(border=True):
                st.markdown(f"**{ticket['subject']}**")
                st.caption(f"{ticket['DXer']} · {ticket['category']} · {ticket['created_utc']}")
                st.write(ticket["details"])
                with st.form(f"admin_ticket_{selected_id}"):
                    statuses = ["Open", "In progress", "Waiting on DXer", "Resolved", "Closed"]
                    status = st.selectbox(
                        "Status",
                        statuses,
                        index=statuses.index(ticket["status"]) if ticket["status"] in statuses else 0,
                    )
                    comment = st.text_area(
                        "Most recent administrator comment", value=str(ticket["admin_comment"])
                    )
                    save = st.form_submit_button("Update ticket", icon=":material/save:", type="primary")
                if save:
                    updated, message = store.update_support_ticket(
                        selected_id, status=status, admin_comment=comment
                    )
                    if updated:
                        st.session_state.admin_notice = message
                        st.rerun()
                    st.error(message)

else:
    st.subheader("Station review queue")
    reviews = store.station_review_logs()
    if reviews.empty:
        st.caption("No manual or approved-unlisted stations are waiting for review.")
    else:
        names = display_names()
        reviews = reviews.copy()
        reviews["DXer"] = reviews["user_id"].map(lambda value: names.get(str(value), "DXer"))
        st.dataframe(
            reviews[
                ["log_id", "DXer", "band", "frequency", "call", "station_city", "station_region", "station_country", "source", "station_review_status"]
            ],
            hide_index=True,
        )
        ids = reviews["log_id"].astype(str).tolist()
        selected_id = st.selectbox(
            "Reception to review",
            ids,
            format_func=lambda value: (
                lambda row: f"{row['call']} · {row['frequency']} · {row['station_city']}, {row['station_region']}"
            )(reviews[reviews["log_id"] == value].iloc[0]),
        )
        record = reviews[reviews["log_id"] == selected_id].iloc[0]
        statuses = ["Pending", "Needs database addition", "Reviewed", "Dismissed"]
        status = st.selectbox(
            "Review status",
            statuses,
            index=statuses.index(record["station_review_status"])
            if record["station_review_status"] in statuses
            else 0,
        )
        if st.button("Update station review", icon=":material/save:", type="primary"):
            updated, message = store.update_station_review_status(selected_id, status)
            if updated:
                st.session_state.admin_notice = message
                st.rerun()
            st.error(message)
