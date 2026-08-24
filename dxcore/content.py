from __future__ import annotations

import re
from datetime import datetime, timezone

import pandas as pd

from dxcore.config import CONTENT_DIR
from dxcore.metrics import canonical_daypart


CHALLENGE_FILE = CONTENT_DIR / "challenge_schedule.csv"
ANNOUNCEMENT_FILE = CONTENT_DIR / "announcements.csv"


def _text(value: object) -> str:
    return "" if pd.isna(value) else str(value).strip()


def _enabled(value: object) -> bool:
    return _text(value).lower() not in {"", "0", "false", "no", "off"}


def _items(value: object) -> list[str]:
    return [item.strip() for item in re.split(r"[|;]", _text(value)) if item.strip()]


def _utc(value: object) -> datetime:
    parsed = pd.to_datetime(_text(value), utc=True)
    if pd.isna(parsed):
        raise ValueError(f"Invalid UTC date/time: {value}")
    return parsed.to_pydatetime()


def parse_frequency_spec(value: object) -> str | list[float] | list[tuple[float, float]]:
    text = _text(value).upper()
    if not text or text == "ALL":
        return "ALL"
    singles: list[float] = []
    ranges: list[tuple[float, float]] = []
    for token in _items(text.replace(",", "|")):
        if "-" in token:
            start, end = token.split("-", 1)
            ranges.append((float(start), float(end)))
        else:
            singles.append(float(token))
    if ranges and singles:
        ranges.extend((value, value) for value in singles)
        return ranges
    return ranges or singles


def frequency_allowed(spec: object, frequency: float) -> bool:
    if spec == "ALL":
        return True
    for item in spec if isinstance(spec, list) else []:
        if isinstance(item, tuple):
            if item[0] - 0.001 <= frequency <= item[1] + 0.001:
                return True
        elif abs(float(item) - frequency) < 0.001:
            return True
    return False


def load_challenges() -> list[dict[str, object]]:
    frame = pd.read_csv(CHALLENGE_FILE, dtype=str).fillna("")
    return challenges_from_frame(frame)


def challenges_from_frame(frame: pd.DataFrame) -> list[dict[str, object]]:
    challenges: list[dict[str, object]] = []
    for row in frame.to_dict("records"):
        if not _enabled(row.get("active", "true")):
            continue
        bands = [value.upper() for value in _items(row.get("bands", ""))]
        frequencies = parse_frequency_spec(row.get("frequencies", "ALL"))
        challenge = {
            "id": _text(row.get("challenge_id")),
            "type": _text(row.get("challenge_type")).lower() or "sprint",
            "name": _text(row.get("challenge_name")),
            "timeframe_tag": _text(row.get("timeframe_tag")) or _text(row.get("challenge_name")),
            "start_utc": _utc(row.get("start_utc")),
            "end_utc": _utc(row.get("end_utc")),
            "bands": bands,
            "band": bands[0] if len(bands) == 1 else "Multiple",
            "description": _text(row.get("description")),
            "rules": {
                "frequencies": frequencies,
                "include_countries": _items(row.get("include_countries", "")),
                "exclude_countries": _items(row.get("exclude_countries", "")),
                "include_regions": _items(row.get("include_regions", "")),
                "exclude_regions": _items(row.get("exclude_regions", "")),
                "propagation_modes": _items(row.get("propagation_modes", "")),
                "dayparts": _items(row.get("dayparts", "")),
                "min_distance": float(_text(row.get("min_distance")))
                if _text(row.get("min_distance"))
                else None,
                "max_distance": float(_text(row.get("max_distance")))
                if _text(row.get("max_distance"))
                else None,
            },
            "scoring_method": _text(row.get("scoring_method")) or "Unique stations",
        }
        if challenge["id"] and challenge["name"] and challenge["start_utc"] <= challenge["end_utc"]:
            challenges.append(challenge)
    return challenges


def active_sprints_for_band(band: str, now: datetime | None = None) -> list[dict[str, object]]:
    instant = now or datetime.now(timezone.utc)
    return [
        challenge
        for challenge in load_challenges()
        if challenge["type"] == "sprint"
        and band in challenge["bands"]
        and challenge["start_utc"] <= instant <= challenge["end_utc"]
    ]


def station_qualifies_for_challenge(
    station: pd.Series | dict[str, object], challenge: dict[str, object]
) -> bool:
    """Apply challenge rules that can be known before a reception is submitted."""
    value = dict(station)
    if str(value.get("band", "")).upper() not in challenge["bands"]:
        return False
    rules = challenge["rules"]
    if not frequency_allowed(rules.get("frequencies", "ALL"), float(value.get("frequency", 0))):
        return False
    country = _text(value.get("country", value.get("station_country", ""))).casefold()
    region = _text(value.get("region", value.get("station_region", ""))).casefold()
    includes = {item.casefold() for item in rules.get("include_countries", [])}
    excludes = {item.casefold() for item in rules.get("exclude_countries", [])}
    include_regions = {item.casefold() for item in rules.get("include_regions", [])}
    exclude_regions = {item.casefold() for item in rules.get("exclude_regions", [])}
    if includes and country not in includes:
        return False
    if country in excludes:
        return False
    if include_regions and region not in include_regions:
        return False
    if region in exclude_regions:
        return False
    distance = pd.to_numeric(value.get("distance_miles"), errors="coerce")
    minimum = rules.get("min_distance")
    maximum = rules.get("max_distance")
    if minimum is not None and (pd.isna(distance) or float(distance) < float(minimum)):
        return False
    if maximum is not None and (pd.isna(distance) or float(distance) > float(maximum)):
        return False
    return True


def log_qualifies(log: pd.Series | dict[str, object], challenge: dict[str, object]) -> bool:
    value = dict(log)
    station_view = {
        "band": value.get("band", ""),
        "frequency": value.get("frequency", 0),
        "country": value.get("station_country", ""),
        "region": value.get("station_region", ""),
        "distance_miles": value.get("distance_miles", ""),
    }
    if not station_qualifies_for_challenge(station_view, challenge):
        return False
    reception = pd.to_datetime(value.get("reception_utc"), utc=True).to_pydatetime()
    if not challenge["start_utc"] <= reception <= challenge["end_utc"]:
        return False
    rules = challenge["rules"]
    propagation = _text(value.get("propagation")).casefold()
    modes = {item.casefold() for item in rules.get("propagation_modes", [])}
    dayparts = {canonical_daypart(item).casefold() for item in rules.get("dayparts", [])}
    if modes and propagation not in modes:
        return False
    if dayparts and canonical_daypart(propagation).casefold() not in dayparts:
        return False
    return True


def load_announcements(now: datetime | None = None) -> pd.DataFrame:
    frame = pd.read_csv(ANNOUNCEMENT_FILE, dtype=str).fillna("")
    if "body" not in frame and "message" in frame:
        frame["body"] = frame["message"]
    return active_announcements(frame, now)


def active_announcements(frame: pd.DataFrame, now: datetime | None = None) -> pd.DataFrame:
    instant = now or datetime.now(timezone.utc)
    if frame.empty:
        return frame
    frame = frame[frame["active"].map(_enabled)].copy()
    frame["start"] = pd.to_datetime(frame["start_utc"], utc=True, errors="coerce")
    frame["end"] = pd.to_datetime(frame["end_utc"], utc=True, errors="coerce")
    timestamp = pd.Timestamp(instant)
    frame = frame[(frame["start"].isna() | (frame["start"] <= timestamp)) & (frame["end"].isna() | (frame["end"] >= timestamp))]
    return frame.sort_values("start", ascending=False, na_position="last")
