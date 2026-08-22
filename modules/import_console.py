from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from app_support import bandscan_progress, get_station_data, get_store
from dxcore.importers import (
    NOT_MAPPED,
    import_batch_id,
    log_payloads,
    mapping_for_format,
    normalize_import,
    read_upload,
)


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
            "Combined date/time takes precedence when mapped. Otherwise both reception date and reception time are required."
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
        st.metric("Bandscan locked", f"{counts.get('Bandscan locked', 0):,}", border=True)
        st.metric("Invalid", f"{counts.get('Invalid', 0):,}", border=True)


def render_import_console(location: dict[str, object]) -> None:
    st.subheader("Bulk import")
    st.caption(
        "Upload your own reception log. The importer normalizes it against the Season 7 station lists, then requires a reviewed preview before writing anything."
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
            time_label = first[1].selectbox(
                "Timestamp protocol",
                ["UTC", "Local time"],
                key=f"bulk_import_time_protocol_{file_token}",
            )
            time_protocol = "UTC" if time_label == "UTC" else "Local"
        browser_zone = str(getattr(st.context, "timezone", "") or "America/Chicago")
        timezone_name = first[2].text_input(
            "IANA time zone",
            value="UTC" if time_protocol == "UTC" else browser_zone,
            disabled=time_protocol == "UTC",
            key=f"bulk_import_timezone_{file_token}",
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
    if problems:
        for problem in problems:
            st.warning(problem)
        return

    review_key = f"bulk_import_review_{file_token}"
    if st.button(
        "Build reviewed preview",
        icon=":material/rule:",
        type="primary",
        key=f"bulk_import_process_{file_token}",
    ):
        store = get_store()
        unlocked = {
            band
            for band in ("MW", "FM", "NWR")
            if bandscan_progress(str(location["location_id"]), band)[2] == 1
        }
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
                unlocked_bands=unlocked,
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

    st.subheader("Import review")
    _status_metrics(review)
    st.caption(
        "Only green-ready rows can be selected. Duplicate, ambiguous, locked, and invalid rows are never written."
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
