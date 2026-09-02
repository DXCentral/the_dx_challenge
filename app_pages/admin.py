from __future__ import annotations

from datetime import date, datetime, time, timezone

import pandas as pd
import streamlit as st

from app_support import display_names, get_station_data, get_store, require_admin_access
from dxcore.content import parse_frequency_spec
from dxcore.geo import haversine_miles, latlon_to_grid
from dxcore.metrics import canonical_daypart
from dxcore.propagation import (
    ALL_PROPAGATION_OPTIONS,
    FM_NWR_PROPAGATION_OPTIONS,
    MW_PROPAGATION_OPTIONS,
)


def as_datetime(value: object, fallback: datetime) -> datetime:
    parsed = pd.to_datetime(value, utc=True, errors="coerce")
    return fallback if pd.isna(parsed) else parsed.to_pydatetime()


def utc_value(day: date, clock: time) -> str:
    return datetime.combine(day, clock, tzinfo=timezone.utc).replace(second=0, microsecond=0).isoformat()


def as_bool(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


@st.dialog("Confirm deletion")
def confirm_delete(kind: str, record_id: str, label: str, owner_id: str = "") -> None:
    st.warning(f"Delete {kind.lower()} **{label}**? This cannot be undone.")
    if st.button("Delete permanently", icon=":material/delete:", type="primary"):
        if kind == "Announcement":
            deleted, message = get_store().delete_announcement(record_id)
        elif kind == "Reception":
            deleted, message = get_store().delete_log(owner_id, record_id)
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
    propagation_options = ALL_PROPAGATION_OPTIONS
    legacy_daypart_labels = {
        "Daytime": "Groundwave / Daytime",
        "Sunrise grayline": "Sunrise grayline",
        "Sunset grayline": "Sunset grayline",
        "Nighttime": "Skywave / Nighttime",
    }
    stored_propagation = str(record.get("propagation_modes", "")).split("|")
    stored_dayparts = str(record.get("dayparts", "")).split("|")
    propagation_defaults = [
        value for value in [
            *stored_propagation,
            *(legacy_daypart_labels.get(value, value) for value in stored_dayparts),
        ]
        if value in propagation_options
    ]
    propagation_defaults = list(dict.fromkeys(propagation_defaults))
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
            "Propagation modes / MW dayparts",
            propagation_options,
            default=propagation_defaults,
            help="MW Sunrise, Daytime, Sunset, and Nighttime choices live here with the FM/NWR propagation modes.",
        )
        dayparts = [
            canonical_daypart(value)
            for value in propagation_modes
            if value in MW_PROPAGATION_OPTIONS
        ]
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
        reviews["Related reports"] = reviews.groupby("station_id")["log_id"].transform("size")
        reviews = reviews.sort_values(["call", "frequency", "reception_utc", "log_id"])
        st.caption(
            "Reception UTC is shown so repeated reports can be reviewed chronologically. "
            "Adding one station to the managed database resolves every related report with the same station ID."
        )
        st.dataframe(
            reviews[
                [
                    "log_id", "DXer", "reception_utc", "band", "frequency", "call",
                    "station_city", "station_region", "station_country", "source",
                    "Related reports", "station_review_status",
                ]
            ],
            hide_index=True,
            column_config={
                "reception_utc": st.column_config.DatetimeColumn(
                    "Reception (UTC)", format="YYYY-MM-DD HH:mm"
                ),
            },
        )
        ids = reviews["log_id"].astype(str).tolist()
        selected_id = st.selectbox(
            "Reception to review",
            ids,
            format_func=lambda value: (
                lambda row: (
                    f"{row['reception_utc']} · {row['call']} · {row['frequency']} · "
                    f"{row['station_city']}, {row['station_region']} · {row['DXer']}"
                )
            )(reviews[reviews["log_id"] == value].iloc[0]),
        )
        record = reviews[reviews["log_id"] == selected_id].iloc[0]
        related = reviews[reviews["station_id"].astype(str) == str(record["station_id"])]
        st.caption(
            f"{len(related):,} related review report(s) · earliest reception "
            f"{related['reception_utc'].min()}"
        )
        if st.button(
            "Delete selected reception",
            icon=":material/delete:",
            help="Use this for a later duplicate or an invalid report. The deletion is synchronized to the Google Sheet.",
        ):
            confirm_delete(
                "Reception",
                selected_id,
                f"{record['reception_utc']} · {record['call']} · {record['frequency']}",
                str(record["user_id"]),
            )

        station_data = get_station_data()
        candidates = station_data[
            station_data["band"].astype(str).str.upper().eq(str(record["band"]).upper())
        ].copy()
        try:
            tolerance = 0.11 if str(record["band"]).upper() == "MW" else 0.051
            candidates = candidates[
                (pd.to_numeric(candidates["frequency"], errors="coerce") - float(record["frequency"])).abs()
                <= tolerance
            ]
        except (TypeError, ValueError):
            candidates = candidates.iloc[0:0]
        exact_call = candidates[
            candidates["call"].astype(str).str.casefold() == str(record["call"]).casefold()
        ]
        if not exact_call.empty:
            candidates = exact_call
        candidates = candidates.sort_values(["frequency", "call", "city"]).head(100)
        candidate_records = {
            str(row["station_id"]): row for row in candidates.to_dict("records")
        }
        candidate_options = ["__current__", *candidate_records]
        reception = as_datetime(record["reception_utc"], datetime.now(timezone.utc))
        propagation_options = (
            MW_PROPAGATION_OPTIONS
            if str(record["band"]).upper() == "MW"
            else FM_NWR_PROPAGATION_OPTIONS
        )
        current_propagation = str(record["propagation"])
        if current_propagation not in propagation_options:
            propagation_options = [current_propagation, *propagation_options]

        with st.form(f"admin_edit_reception_{selected_id}"):
            st.markdown("**Administrator reception editor**")
            canonical_id = st.selectbox(
                "Canonical station match (optional)",
                candidate_options,
                format_func=lambda value: (
                    "Keep and edit the current station"
                    if value == "__current__"
                    else (
                        lambda station: (
                            f"{station['call']} · {station['frequency']} · "
                            f"{station['city']}, {station['region']}, {station['country']}"
                        )
                    )(candidate_records[value])
                ),
                help="Choosing a canonical match replaces the uploaded station fields when you save.",
            )
            columns = st.columns(3)
            band_value = columns[0].selectbox(
                "Band", ["MW", "FM", "NWR"],
                index=["MW", "FM", "NWR"].index(str(record["band"]).upper()),
            )
            frequency_value = columns[1].number_input(
                "Frequency", value=float(record["frequency"]), step=0.001, format="%.3f"
            )
            call_value = columns[2].text_input("Call / station name", value=str(record["call"]))
            columns = st.columns(3)
            city_value = columns[0].text_input("Station city", value=str(record["station_city"]))
            region_value = columns[1].text_input("State / province", value=str(record["station_region"]))
            country_value = columns[2].text_input("Country", value=str(record["station_country"]))
            columns = st.columns(3)
            county_value = columns[0].text_input("County / parish", value=str(record["station_county"]))
            grid_value = columns[1].text_input("Station grid", value=str(record["station_grid"]))
            propagation_value = columns[2].selectbox(
                "Propagation / MW daypart",
                propagation_options,
                index=propagation_options.index(current_propagation),
            )
            columns = st.columns(2)
            latitude_value = columns[0].text_input(
                "Station latitude", value=str(record["station_latitude"])
            )
            longitude_value = columns[1].text_input(
                "Station longitude", value=str(record["station_longitude"])
            )
            columns = st.columns(2)
            reception_date = columns[0].date_input("Reception date (UTC)", value=reception.date())
            reception_time = columns[1].time_input(
                "Reception time (UTC)", value=reception.time().replace(tzinfo=None)
            )
            flags = st.columns(2)
            is_sdr = flags[0].checkbox("Received using an SDR", value=bool(record["is_sdr"]))
            is_portable = flags[1].checkbox("Portable operation", value=bool(record["is_portable"]))
            notes = st.text_area("Notes", value=str(record["notes"]))
            save_reception = st.form_submit_button(
                "Save reception corrections", icon=":material/edit:", type="primary"
            )
        if save_reception:
            selected_station = candidate_records.get(canonical_id)
            if selected_station:
                station_values = {
                    "station_id": selected_station["station_id"],
                    "band": selected_station["band"],
                    "frequency": selected_station["frequency"],
                    "call": selected_station["call"],
                    "station_city": selected_station["city"],
                    "station_region": selected_station["region"],
                    "station_country": selected_station["country"],
                    "station_county": selected_station["county"],
                    "station_grid": selected_station["grid"],
                    "station_latitude": selected_station["latitude"],
                    "station_longitude": selected_station["longitude"],
                }
            else:
                station_values = {
                    "station_id": record["station_id"],
                    "band": band_value,
                    "frequency": frequency_value,
                    "call": call_value.strip(),
                    "station_city": city_value.strip(),
                    "station_region": region_value.strip(),
                    "station_country": country_value.strip(),
                    "station_county": county_value.strip(),
                    "station_grid": grid_value.strip().upper(),
                    "station_latitude": latitude_value.strip(),
                    "station_longitude": longitude_value.strip(),
                }
            updated, message = store.admin_update_log(
                selected_id,
                {
                    **station_values,
                    "reception_utc": utc_value(reception_date, reception_time),
                    "propagation": propagation_value,
                    "is_sdr": is_sdr,
                    "is_portable": is_portable,
                    "notes": notes,
                },
            )
            if updated:
                st.session_state.admin_notice = message
                st.rerun()
            st.error(message)

        statuses = ["Pending", "Needs database addition", "Reviewed", "Dismissed"]
        status = st.selectbox(
            "Review status",
            statuses,
            index=statuses.index(record["station_review_status"])
            if record["station_review_status"] in statuses
            else 0,
            help="Saving 'Needs database addition' immediately adds the corrected station to the managed station database and creates or updates the private Station Overrides Sheet tab.",
        )
        if st.button("Save review decision", icon=":material/save:", type="primary"):
            if status == "Needs database addition":
                updated, message, _ = store.promote_station_override(selected_id)
            else:
                updated, message = store.update_station_review_status(selected_id, status)
            if updated:
                st.session_state.admin_notice = message
                st.rerun()
            st.error(message)

        managed = store.station_overrides()
        st.caption(f"{len(managed):,} administrator-approved station addition(s) are currently active.")
