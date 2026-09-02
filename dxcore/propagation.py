from __future__ import annotations

import re
import unicodedata


MW_PROPAGATION_OPTIONS = [
    "Groundwave / Daytime",
    "Sunrise grayline",
    "Sunset grayline",
    "Skywave / Nighttime",
]

FM_NWR_PROPAGATION_OPTIONS = [
    "Local",
    "Tropo",
    "Meteor Scatter",
    "Sporadic E",
    "Aurora",
    "Aircraft Scatter",
    "Other",
]

ALL_PROPAGATION_OPTIONS = [*MW_PROPAGATION_OPTIONS, *FM_NWR_PROPAGATION_OPTIONS]


def _token(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def normalize_mw_propagation(value: object) -> str:
    """Return the shared MW propagation/daypart label or an empty string."""
    token = _token(value)
    if token in {"DAY", "DAYTIME", "GROUNDWAVE", "GROUNDWAVEDAYTIME", "GW"}:
        return "Groundwave / Daytime"
    if token in {"SUNRISE", "SUNRISEGRAYLINE", "SUNRISEGREYLINE", "SR"}:
        return "Sunrise grayline"
    if token in {"SUNSET", "SUNSETGRAYLINE", "SUNSETGREYLINE", "SS"}:
        return "Sunset grayline"
    if token in {"NIGHT", "NIGHTTIME", "SKYWAVE", "SKYWAVENIGHTTIME", "SW"}:
        return "Skywave / Nighttime"
    return ""

