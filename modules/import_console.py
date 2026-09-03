from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import pandas as pd
import streamlit as st
from geopy.geocoders import Nominatim

from app_support import get_station_data, get_store
from dxcore.geo import grid_to_latlon, latlon_to_grid
from dxcore.importers import (
    NOT_MAPPED,
    import_batch_id,
    log_payloads,
    mapping_for_format,
    normalize_import,
    read_upload,
    resolve_matching_review_rows,
    unlisted_station_id,
)
from dxcore.propagation import MW_DAYPART_HELP


MAPPING_LABELS = {
    "band": "Band",
    "frequency": "Frequency",
    "call": "Call sign / station",
    "timestamp": "Combined date/time",
    "date": "Reception date",
    "time": "Reception time",
    "city": "Station city",
    "region": "State / province",
    "country": "Country / ITU",
    "county": "County / parish",
    "grid": "Grid",
    "propagation": "Propagation / mode",
    "notes": "Notes / remarks",
    "is_sdr": "SDR used",
    "is_portable": "Portable operation",
}


def clear_import_state() -> None:
    for key in list(st.session_state):
        if key.startswith("bulk_import_"):
            st.session_state.pop(key, None)


@st.cache_data(max_entries=8, show_spinner=False)
def cached_read_upload(file_name: str, raw: bytes):
    return read_upload(file_name, raw)


def _mapping_widgets(
    source_format: str, columns: list[str], file_token: str
) -> dict[str, str]:
    defaults = mapping_for_format(source_format, columns)
    options = [NOT_MAPPED, *columns]
    mapping: dict[str, str] = {}
    expander = st.expander(
        "Review field mapping",
        expanded=source_format == "Custom",
        icon=":material/account_tree:",
    )
    with expander:
        st.caption(
            "Combined date/time takes precedence when mapped. Otherwise both reception date and reception time are required. "
            "Generic form-submission Timestamp columns are intentionally left unmapped for Custom imports."
        )
        fields = list(MAPPING_LABELS)
        for start in range(0, len(fields), 3):
            columns_ui = st.columns(3)
            for column_ui, field in zip(columns_ui, fields[start : start + 3], strict=False):
                default = defaults.get(field, NOT_MAPPED)
                index = options.index(default) if default in options else 0
                mapping[field] = column_ui.selectbox(
                    MAPPING_LABELS[field],
                    options,
                    index=index,
                    key=f"bulk_import_map_{file_token}_{source_format}_{field}",
                )
    return mapping


def _validate_mapping(mapping: dict[str, str]) -> list[str]:
    problems: list[str] = []
    if mapping.get("frequency") == NOT_MAPPED:
        problems.append("Map a frequency column.")
    if mapping.get("call") == NOT_MAPPED:
        problems.append("Map a call sign or station column.")
    has_timestamp = mapping.get("timestamp") != NOT_MAPPED
    has_date_time = (
        mapping.get("date") != NOT_MAPPED and mapping.get("time") != NOT_MAPPED
    )
    if not has_timestamp and not has_date_time:
        problems.append("Map either a combined date/time column or separate date and time columns.")
    return problems


def _status_metrics(review: pd.DataFrame) -> None:
    counts = review["status"].value_counts().to_dict()
    with st.container(horizontal=True):
        st.metric("Ready", f"{counts.get('Ready', 0):,}", border=True)
        st.metric("Duplicates", f"{counts.get('Duplicate', 0):,}", border=True)
        st.metric("Needs review", f"{counts.get('Needs review', 0):,}", border=True)
        st.metric("Invalid", f"{counts.get('Invalid', 0):,}", border=True)


def _review_held_rows(
    review: pd.DataFrame,
    *,
    review_key: str,
    file_token: str,
    location: dict[str, object],
) -> None:
    held = review[review["status"] == "Needs review"]
    if held.empty:
        return
    st.subheader("Resolve held rows")
    st.caption(
        "Select a held row, confirm a suggested canonical station, or approve it as unlisted. Nothing is imported until it becomes Ready and is selected in the main review table."
    )
    held_view = held[
        [
            "source_row", "band", "frequency", "source_station", "source_city",
            "source_region", "source_country", "reception_utc", "message",
        ]
    ]
    event = st.dataframe(
        held_view,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=f"bulk_import_held_{file_token}",
        column_config={
            "source_row": st.column_config.NumberColumn("Source row", format="%d"),
            "reception_utc": st.column_config.DatetimeColumn(
                "Reception (UTC)", format="YYYY-MM-DD HH:mm"
            ),
        },
    )
    if not event.selection.rows:
        return
    selected_position = event.selection.rows[0]
    if selected_position >= len(held):
        return
    row_index = held.index[selected_position]
    row = review.loc[row_index]
    suggestion_ids = [
        value for value in str(row.get("suggestion_ids", "")).split("|") if value
    ]
    suggestion_labels = [
        value for value in str(row.get("suggestion_labels", "")).split("|") if value
    ]
    station_data = get_station_data()
    station_lookup = {
        str(record["station_id"]): record
        for record in station_data[station_data["station_id"].isin(suggestion_ids)].to_dict("records")
    }
    with st.container(border=True):
        st.markdown(
            f"**Source row {int(row['source_row'])}: {row['source_station']}** · "
            f"{row['frequency']} · {row.get('source_city', '')}, {row.get('source_region', '')}, {row.get('source_country', '')}"
        )
        if suggestion_ids:
            labels = dict(zip(suggestion_ids, suggestion_labels, strict=False))
            candidate_id = st.selectbox(
                "Suggested canonical match",
                suggestion_ids,
                format_func=lambda value: labels.get(value, value),
                key=f"bulk_import_suggestion_{file_token}_{row_index}",
            )
            if st.button(
                "Confirm suggested station",
                icon=":material/check_circle:",
                type="primary",
                key=f"bulk_import_confirm_suggestion_{file_token}_{row_index}",
            ):
                station = station_lookup.get(candidate_id)
                if station is None:
                    st.error("That station-list candidate is no longer available.")
                else:
                    resolved, count = resolve_matching_review_rows(
                        review,
                        row_index,
                        station,
                        location=location,
                        existing_logs=get_store().logs(st.session_state.user["user_id"]),
                    )
                    st.session_state[review_key] = resolved
                    st.session_state[f"{review_key}_resolution_notice"] = (
                        f"Applied the canonical station to {count:,} matching held row(s)."
                    )
                    st.rerun()
        else:
            st.caption("No safe station-list suggestion was found for this row.")

        unlisted = st.toggle(
            "Approve as an unlisted station",
            key=f"bulk_import_unlisted_toggle_{file_token}_{row_index}",
            help="Use this only after checking the uploaded station details. The resulting reception is flagged for administrator review.",
        )
        if unlisted:
            with st.form(f"bulk_import_unlisted_form_{file_token}_{row_index}"):
                columns = st.columns(2)
                call = columns[0].text_input("Station call / name", value=str(row["source_station"]))
                city = columns[1].text_input("Station city", value=str(row.get("source_city", "")))
                columns = st.columns(2)
                region = columns[0].text_input("State / province / region", value=str(row.get("source_region", "")))
                country = columns[1].text_input("Country", value=str(row.get("source_country", "")))
                columns = st.columns(2)
                county = columns[0].text_input("County / parish", value=str(row.get("source_county", "")))
                grid = columns[1].text_input("Grid (if known)", value=str(row.get("source_grid", ""))).upper()
                approve = st.form_submit_button(
                    "Approve and queue for admin review",
                    icon=":material/playlist_add_check:",
                    type="primary",
                )
            if approve:
                if not call.strip() or not city.strip() or not country.strip():
                    st.error("Station name, city, and country are required.")
                else:
                    latitude = longitude = None
                    resolved_grid = grid.strip()
                    try:
                        if resolved_grid:
                            latitude, longitude = grid_to_latlon(resolved_grid)
                        else:
                            query = ", ".join(
                                value.strip()
                                for value in (city, region, country)
                                if value.strip()
                            )
                            result = Nominatim(
                                user_agent="dx_challenge_s7_import_review", timeout=8
                            ).geocode(query)
                            if result is not None:
                                latitude, longitude = float(result.latitude), float(result.longitude)
                                resolved_grid = latlon_to_grid(latitude, longitude)
                    except (OSError, ValueError):
                        latitude = longitude = None
                    station = {
                        "station_id": unlisted_station_id(
                            str(row["band"]), float(row["frequency"]), call, city, region, country
                        ),
                        "band": row["band"],
                        "frequency": float(row["frequency"]),
                        "call": call.strip(),
                        "city": city.strip(),
                        "region": region.strip(),
                        "country": country.strip(),
                        "county": county.strip(),
                        "grid": resolved_grid,
                        "latitude": latitude,
                        "longitude": longitude,
                    }
                    resolved, count = resolve_matching_review_rows(
                        review,
                        row_index,
                        station,
                        location=location,
                        existing_logs=get_store().logs(st.session_state.user["user_id"]),
                        unlisted=True,
                    )
                    st.session_state[review_key] = resolved
                    st.session_state[f"{review_key}_resolution_notice"] = (
                        f"Approved {count:,} matching held row(s) as the same unlisted station."
                    )
                    st.rerun()


def render_import_console(location: dict[str, object]) -> None:
    st.subheader("Bulk import")
    st.caption(
        "Upload your own reception log. The importer normalizes it against the Season 7 station lists, then requires a reviewed preview before writing anything."
    )
    st.caption(
        "MW dayparts are calculated automatically from each reception's date/time and the selected operating QTH. "
        + MW_DAYPART_HELP
    )
    uploaded = st.file_uploader(
        "Reception log file",
        type=["csv", "tsv", "txt", "xlsx"],
        key="bulk_import_upload",
        help="Supported presets: FMList, MWList, and WLogger. Other files can be mapped as Custom.",
    )
    if uploaded is None:
        st.info(
            "Choose an FMList, MWList, WLogger, CSV, TSV, or XLSX export to begin.",
            icon=":material/upload_file:",
        )
        return

    raw = uploaded.getvalue()
    file_token = hashlib.sha1(raw).hexdigest()[:12]
    try:
        parsed = cached_read_upload(uploaded.name, raw)
    except ValueError as error:
        st.error(str(error))
        return

    format_options = ["FMList", "MWList", "WLogger", "Custom"]
    detected = parsed.detected_format if parsed.detected_format in format_options else "Custom"
    with st.container(horizontal=True, vertical_alignment="center"):
        st.badge(
            f"Detected: {detected}",
            icon=":material/check_circle:" if detected != "Custom" else ":material/schema:",
            color="green" if detected != "Custom" else "blue",
        )
        st.caption(f"{len(parsed.frame):,} source rows · {len(parsed.frame.columns):,} columns")
        st.button(
            "Clear importer",
            icon=":material/restart_alt:",
            on_click=clear_import_state,
            key="bulk_import_clear",
        )
    for warning in parsed.warnings:
        st.caption(warning)

    source_format = st.selectbox(
        "Import format",
        format_options,
        index=format_options.index(detected),
        key=f"bulk_import_format_{file_token}",
        help="Override detection only when you know the file uses another format.",
    )
    mapping = _mapping_widgets(source_format, list(parsed.frame.columns), file_token)

    with st.container(border=True):
        st.markdown("**Date, time, and operating defaults**")
        first = st.columns(3)
        if source_format in {"FMList", "MWList"}:
            first[0].text_input("Date protocol", value="DD.MM.YY (source standard)", disabled=True)
            first[1].text_input("Time protocol", value="UTC (source standard)", disabled=True)
            date_order = "DMY"
            time_protocol = "UTC"
        else:
            date_label = first[0].selectbox(
                "Date protocol",
                ["Month / day / year", "Day / month / year", "Year / month / day"],
                key=f"bulk_import_date_order_{file_token}",
                help="This is explicit so ambiguous dates such as 04/05/2026 are never silently swapped.",
            )
            date_order = {
                "Month / day / year": "MDY",
                "Day / month / year": "DMY",
                "Year / month / day": "YMD",
            }[date_label]
            time_protocol_key = f"bulk_import_time_protocol_{file_token}"
            time_label = first[1].selectbox(
                "Timestamp protocol",
                ["UTC", "Local time"],
                key=time_protocol_key,
            )
            time_protocol = "UTC" if time_label == "UTC" else "Local"
        browser_zone = str(getattr(st.context, "timezone", "") or "America/Chicago")
        timezone_key = f"bulk_import_timezone_{file_token}"
        protocol_state_key = f"{timezone_key}_protocol"
        if st.session_state.get(protocol_state_key) != time_protocol:
            st.session_state[timezone_key] = "UTC" if time_protocol == "UTC" else browser_zone
            st.session_state[protocol_state_key] = time_protocol
        timezone_name = first[2].text_input(
            "IANA time zone",
            disabled=time_protocol == "UTC",
            key=timezone_key,
            help="Examples: America/Chicago, America/New_York, Europe/London.",
        )
        second = st.columns(4)
        fixed_band = second[0].selectbox(
            "Band when not mapped",
            ["Auto-detect", "MW", "FM", "NWR"],
            key=f"bulk_import_fixed_band_{file_token}",
        )
        default_propagation = second[1].selectbox(
            "Default FM/NWR propagation",
            ["Other", "Local", "Tropo", "Meteor Scatter", "Sporadic E", "Aurora", "Aircraft Scatter"],
            key=f"bulk_import_default_prop_{file_token}",
        )
        st.session_state.setdefault("bulk_import_default_sdr", False)
        st.session_state.setdefault(
            "bulk_import_default_portable", not bool(location["is_home"])
        )
        default_is_sdr = second[2].toggle(
            "Received using an SDR",
            key="bulk_import_default_sdr",
            persist_state="session",
        )
        default_is_portable = second[3].toggle(
            "Portable operation",
            key="bulk_import_default_portable",
            persist_state="session",
        )

    problems = _validate_mapping(mapping)
    generic_timestamp = (
        source_format == "Custom"
        and str(mapping.get("timestamp", "")).strip().casefold() == "timestamp"
    )
    timestamp_confirmed = True
    if generic_timestamp:
        st.warning(
            "The mapped column is named only 'Timestamp'. In Google Forms exports this is usually the form-submission time, "
            "not the reception time. Map the separate reception date/time fields unless this column truly contains reception times."
        )
        timestamp_confirmed = st.checkbox(
            "I confirm that Timestamp contains the reception date and time.",
            key=f"bulk_import_generic_timestamp_confirm_{file_token}",
        )
    if problems:
        for problem in problems:
            st.warning(problem)
        return

    review_key = f"bulk_import_review_{file_token}"
    if st.button(
        "Build reviewed preview",
        icon=":material/rule:",
        type="primary",
        disabled=not timestamp_confirmed,
        key=f"bulk_import_process_{file_token}",
    ):
        store = get_store()
        with st.spinner("Normalizing stations, timestamps, and duplicates…"):
            review = normalize_import(
                parsed.frame,
                source_format=source_format,
                mapping=mapping,
                date_order=date_order,
                time_protocol=time_protocol,
                timezone_name=timezone_name or "UTC",
                fixed_band="" if fixed_band == "Auto-detect" else fixed_band,
                default_propagation=default_propagation,
                default_is_sdr=default_is_sdr,
                default_is_portable=default_is_portable,
                user_id=st.session_state.user["user_id"],
                location=location,
                stations=get_station_data(),
                existing_logs=store.logs(st.session_state.user["user_id"]),
            )
        st.session_state[review_key] = review
        st.session_state[f"{review_key}_settings"] = {
            "source_format": source_format,
            "date_order": date_order,
            "time_protocol": time_protocol,
            "timezone_name": timezone_name or "UTC",
            "filename": uploaded.name,
        }

    review = st.session_state.get(review_key)
    if not isinstance(review, pd.DataFrame):
        return

    if resolution_notice := st.session_state.pop(f"{review_key}_resolution_notice", None):
        st.success(resolution_notice)

    st.subheader("Import review")
    _status_metrics(review)
    st.caption(
        "Only green-ready rows can be selected. Duplicate and invalid rows are never written; held rows can be resolved below."
    )
    display_columns = [
        "selected", "status", "source_row", "band", "frequency", "source_station",
        "call", "station_city", "station_region", "station_country", "reception_utc",
        "propagation", "message",
    ]
    available = [column for column in display_columns if column in review.columns]
    editor = st.data_editor(
        review[available],
        hide_index=True,
        num_rows="fixed",
        disabled=[column for column in available if column != "selected"],
        key=f"bulk_import_editor_{file_token}",
        column_config={
            "selected": st.column_config.CheckboxColumn("Import", pinned=True),
            "source_row": st.column_config.NumberColumn("Source row", format="%d"),
            "reception_utc": st.column_config.DatetimeColumn("Reception (UTC)", format="YYYY-MM-DD HH:mm"),
            "frequency": st.column_config.NumberColumn("Frequency", format="%.3f"),
            "source_station": st.column_config.TextColumn("Uploaded station"),
            "call": st.column_config.TextColumn("Canonical station"),
        },
        height=520,
    )
    review = review.copy()
    review["selected"] = editor["selected"].astype(bool)
    review.loc[review["status"] != "Ready", "selected"] = False
    st.session_state[review_key] = review
    _review_held_rows(
        review,
        review_key=review_key,
        file_token=file_token,
        location=location,
    )
    selected_count = int(((review["status"] == "Ready") & review["selected"]).sum())

    confirm = st.checkbox(
        f"I reviewed the {selected_count:,} selected ready row(s).",
        key=f"bulk_import_confirm_{file_token}",
    )
    if st.button(
        f"Import {selected_count:,} selected reception(s)",
        icon=":material/publish:",
        type="primary",
        disabled=not confirm or selected_count == 0,
        key=f"bulk_import_commit_{file_token}",
    ):
        settings = st.session_state.get(f"{review_key}_settings", {})
        batch_id = import_batch_id(
            st.session_state.user["user_id"], uploaded.name, datetime.now(timezone.utc)
        )
        payloads = log_payloads(review, batch_id)
        result = get_store().append_logs(payloads)
        get_store().record_import_batch(
            batch_id=batch_id,
            user_id=st.session_state.user["user_id"],
            filename=uploaded.name,
            source_format=str(settings.get("source_format", source_format)),
            date_protocol=str(settings.get("date_order", date_order)),
            time_protocol=str(settings.get("time_protocol", time_protocol)),
            timezone_name=str(settings.get("timezone_name", timezone_name or "UTC")),
            row_count=len(review),
            accepted_count=int(result["accepted"]),
            status="Completed" if not result["rejected"] else "Completed with duplicates",
        )
        st.session_state[f"bulk_import_result_{file_token}"] = result
        review.loc[review["selected"], "selected"] = False
        st.session_state[review_key] = review
        st.rerun()

    if result := st.session_state.get(f"bulk_import_result_{file_token}"):
        st.success(
            f"Imported {int(result['accepted']):,} reception(s); "
            f"{int(result['rejected']):,} row(s) were rejected by the final duplicate guard."
        )
