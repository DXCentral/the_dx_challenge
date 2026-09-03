from __future__ import annotations

import re
from typing import Any

import pandas as pd


CATEGORY_HEADER = "What is the category of your shoutout? (Check All That Apply)"
SHOUTOUT_CATEGORIES = [
    "1000 Logs Reached",
    "New Louisiana Station Log",
    "New Canadian Province",
    "New Country",
    "New US State",
    "New Goal Achieved",
    "New Latin American Station Logged",
    "New Mexican State",
    "New Milestone Achieved",
    "New Minnesota Station Logged",
    "New Gear",
    "New Log",
    "New Wisconsin Station Logged",
]

CATEGORY_ALIASES = {
    "new latin american station": "New Latin American Station Logged",
    "new latin american station log": "New Latin American Station Logged",
}

CATEGORY_PRESENTATION: dict[str, tuple[str, str]] = {
    "1000 Logs Reached": (":material/counter_9:", "violet"),
    "New Louisiana Station Log": (":material/location_on:", "orange"),
    "New Canadian Province": (":material/public:", "red"),
    "New Country": (":material/globe:", "blue"),
    "New US State": (":material/map:", "blue"),
    "New Goal Achieved": (":material/flag:", "green"),
    "New Latin American Station Logged": (":material/radio:", "orange"),
    "New Mexican State": (":material/map:", "red"),
    "New Milestone Achieved": (":material/trophy:", "green"),
    "New Minnesota Station Logged": (":material/location_on:", "blue"),
    "New Gear": (":material/settings_input_antenna:", "violet"),
    "New Log": (":material/add_task:", "green"),
    "New Wisconsin Station Logged": (":material/location_on:", "red"),
}


def _clean(value: Any) -> str:
    return "" if value is None or pd.isna(value) else str(value).strip()


def _find_column(frame: pd.DataFrame, candidates: list[str]) -> str | None:
    lookup = {str(column).strip().casefold(): str(column) for column in frame.columns}
    for candidate in candidates:
        if candidate.casefold() in lookup:
            return lookup[candidate.casefold()]
    return None


def split_categories(value: object) -> list[str]:
    categories: list[str] = []
    # WPForms serializes checkbox choices one per line. Do not split on commas:
    # legacy "Something Else (...)" labels contain explanatory comma-separated text.
    for item in re.split(r"[\r\n|]+", _clean(value)):
        label = item.strip()
        if not label:
            continue
        label = CATEGORY_ALIASES.get(label.casefold(), label)
        if label not in categories:
            categories.append(label)
    return categories


def normalize_shoutouts(frame: pd.DataFrame) -> pd.DataFrame:
    """Select only public shoutout fields and normalize WPForms column variants."""
    columns = {
        "entry_id": _find_column(frame, ["Entry ID", "Entry Id", "ID"]),
        "name": _find_column(frame, ["Name", "DXer", "Display Name"]),
        "region": _find_column(frame, ["State/Province/Region", "State / Province / Region", "Region"]),
        "country": _find_column(frame, ["Country"]),
        "categories": _find_column(frame, [CATEGORY_HEADER, "Categories", "Category"]),
        "details": _find_column(frame, ["ShoutOut Details", "Shoutout Details", "Details"]),
        "upload_url": _find_column(
            frame,
            [
                "Do You Have an Aircheck You Want to Share?",
                "Upload?",
                "Upload",
                "Attachment",
            ],
        ),
        "submitted_at": _find_column(
            frame,
            ["Timestamp", "Submission Date", "Date Submitted", "Submitted At", "Entry Date", "Created At"],
        ),
    }
    required = ["entry_id", "name", "categories", "details"]
    missing = [field for field in required if columns[field] is None]
    if missing:
        raise ValueError("The shoutout Sheet is missing required WPForms columns: " + ", ".join(missing))

    normalized = pd.DataFrame(index=frame.index)
    for field in ["entry_id", "name", "region", "country", "details", "upload_url"]:
        source = columns[field]
        normalized[field] = frame[source].map(_clean) if source else ""
    normalized["categories"] = frame[columns["categories"]].map(split_categories)
    date_source = columns["submitted_at"]
    normalized["submitted_at"] = (
        pd.to_datetime(frame[date_source], errors="coerce")
        if date_source
        else pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns]")
    )
    normalized = normalized[
        normalized["name"].ne("") & normalized["details"].ne("")
    ].copy()
    normalized["entry_number"] = pd.to_numeric(normalized["entry_id"], errors="coerce")
    normalized["submission_month"] = normalized["submitted_at"].dt.to_period("M")
    normalized = normalized.sort_values(
        ["submitted_at", "entry_number", "entry_id"],
        ascending=[False, False, False],
        na_position="last",
    ).reset_index(drop=True)
    return normalized


def observed_categories(frame: pd.DataFrame) -> list[str]:
    values = {
        category
        for categories in frame.get("categories", pd.Series(dtype=object))
        for category in (categories if isinstance(categories, list) else [])
    }
    ordered = [category for category in SHOUTOUT_CATEGORIES if category in values]
    return [*ordered, *sorted(values.difference(ordered), key=str.casefold)]
