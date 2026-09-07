from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd


KM_PER_MILE = 1.609344


def uses_local_time(preferences: dict[str, object]) -> bool:
    return str(preferences.get("time_display", "UTC")) == "Local time"


def display_zone(preferences: dict[str, object]) -> ZoneInfo:
    name = str(preferences.get("timezone_name", "UTC")) if uses_local_time(preferences) else "UTC"
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def format_reception(value: object, preferences: dict[str, object]) -> str:
    instant = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(instant):
        return str(value or "")
    local = instant.to_pydatetime().astimezone(display_zone(preferences))
    if str(preferences.get("clock_format", "24-hour")) == "12-hour":
        rendered = local.strftime("%Y-%m-%d %I:%M %p")
    else:
        rendered = local.strftime("%Y-%m-%d %H:%M")
    zone_label = local.tzname() or ("Local" if uses_local_time(preferences) else "UTC")
    return f"{rendered} {zone_label}"


def time_column_label(preferences: dict[str, object]) -> str:
    return "Reception (local)" if uses_local_time(preferences) else "Reception (UTC)"


def distance_is_km(preferences: dict[str, object]) -> bool:
    return str(preferences.get("distance_unit", "Miles")) == "Kilometers"


def convert_distance(value: object, preferences: dict[str, object]) -> float | None:
    parsed = pd.to_numeric(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return float(parsed) * KM_PER_MILE if distance_is_km(preferences) else float(parsed)


def format_distance(value: object, preferences: dict[str, object], decimals: int = 1) -> str:
    converted = convert_distance(value, preferences)
    if converted is None:
        return "Unknown distance"
    unit = "km" if distance_is_km(preferences) else "mi"
    return f"{converted:,.{decimals}f} {unit}"


def distance_column_label(preferences: dict[str, object]) -> str:
    return "Kilometers" if distance_is_km(preferences) else "Miles"


def display_log_table(
    frame: pd.DataFrame, preferences: dict[str, object]
) -> pd.DataFrame:
    """Return a display-only copy while preserving UTC and miles in storage."""
    result = frame.copy()
    if "reception_utc" in result:
        result[time_column_label(preferences)] = result["reception_utc"].map(
            lambda value: format_reception(value, preferences)
        )
        result = result.drop(columns=["reception_utc"])
    if "distance_miles" in result:
        result[distance_column_label(preferences)] = result["distance_miles"].map(
            lambda value: convert_distance(value, preferences)
        )
        result = result.drop(columns=["distance_miles"])
    return result
