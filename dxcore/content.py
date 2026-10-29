from __future__ import annotations

import re
from datetime import datetime, timezone

import pandas as pd

from dxcore.config import CONTENT_DIR
from dxcore.metrics import canonical_daypart, canonical_propagation
from dxcore.propagation import normalize_mw_propagation


CHALLENGE_FILE = CONTENT_DIR / "challenge_schedule.csv"
ANNOUNCEMENT_FILE = CONTENT_DIR / "announcements.csv"
SUPPORTED_BANDS = ("MW", "FM", "NWR")
STATION_ELIGIBILITY_OPTIONS = ("All stations", "New this season only")


def new_season_stations_only(challenge: dict[str, object]) -> bool:
    return (
        challenge.get("type") == "sprint"
        and challenge.get("rules", {}).get("station_eligibility") == "New this season only"
    )


def _season_reception_history(season_logs: pd.DataFrame | None) -> pd.DataFrame:
    columns = ["user_id", "band", "station_id", "reception_utc"]
    if season_logs is None or not set(columns).issubset(season_logs.columns):
        return pd.DataFrame(columns=columns)
    rows = season_logs.copy()
    if "deleted_utc" in rows:
        rows = rows[rows["deleted_utc"].fillna("").astype(str).str.strip().eq("")]
    rows = rows[columns].copy()
    for column in columns[:3]:
        rows[column] = rows[column].fillna("").astype(str).str.strip()
    rows["band"] = rows["band"].str.upper()
    rows["reception_utc"] = pd.to_datetime(
        rows["reception_utc"], utc=True, errors="coerce", format="mixed"
    )
    return rows[
        rows["reception_utc"].notna()
        & rows["user_id"].ne("")
        & rows["station_id"].ne("")
    ]


def previously_heard_station_ids(
    season_logs: pd.DataFrame | None, user_id: str, challenge: dict[str, object]
) -> set[str]:
    """Season history before the sprint, independent of QTH or sprint restrictions."""
    rows = _season_reception_history(season_logs)
    if rows.empty:
        return set()
    return set(rows.loc[
        rows["user_id"].eq(str(user_id))
        & rows["band"].isin(challenge["bands"])
        & rows["reception_utc"].lt(challenge["start_utc"]),
        "station_id",
    ])


def _new_season_reception_mask(
    logs: pd.DataFrame, challenge: dict[str, object], season_logs: pd.DataFrame | None
) -> pd.Series:
    history = _season_reception_history(season_logs)
    if history.empty:
        return pd.Series(False, index=logs.index, dtype=bool)
    keys = ["user_id", "band", "station_id"]
    candidates = logs.reindex(columns=[*keys, "reception_utc"]).copy()
    for column in keys:
        candidates[column] = candidates[column].fillna("").astype(str).str.strip()
    candidates["band"] = candidates["band"].str.upper()
    candidates["reception_utc"] = pd.to_datetime(
        candidates["reception_utc"], utc=True, errors="coerce", format="mixed"
    )
    first = history.groupby(keys)["reception_utc"].min()
    original_dates = pd.Series(
        first.reindex(pd.MultiIndex.from_frame(candidates[keys])).array,
        index=logs.index,
    )
    # A matching station alone is insufficient: this particular reception must
    # satisfy a season marathon too, even if the sprint spans a wider period.
    seasonal = pd.MultiIndex.from_frame(candidates).isin(pd.MultiIndex.from_frame(history))
    return original_dates.between(challenge["start_utc"], challenge["end_utc"]) & seasonal


def _text(value: object) -> str:
    return "" if pd.isna(value) else str(value).strip()


def _enabled(value: object) -> bool:
    return _text(value).lower() not in {"", "0", "false", "no", "off"}


def _items(value: object) -> list[str]:
    return [item.strip() for item in re.split(r"[|;]", _text(value)) if item.strip()]


def ordered_band_options(values: object) -> list[str]:
    """Return unique configured bands in the app's standard display order."""
    if isinstance(values, str):
        candidates = _items(values)
    else:
        try:
            candidates = list(values)  # type: ignore[arg-type]
        except TypeError:
            candidates = []
    normalized = {
        str(value).strip().upper() for value in candidates if str(value).strip()
    }
    return [band for band in SUPPORTED_BANDS if band in normalized] + sorted(
        normalized.difference(SUPPORTED_BANDS)
    )


def challenge_propagation_rules(
    rules: dict[str, object],
) -> tuple[set[str], set[str]]:
    """Split mixed Admin propagation choices into MW and FM/NWR restrictions."""
    mw_dayparts = {
        canonical_daypart(item).casefold()
        for item in rules.get("dayparts", [])
        if canonical_daypart(item)
    }
    fm_nwr_modes: set[str] = set()
    for item in rules.get("propagation_modes", []):
        mw_value = normalize_mw_propagation(item)
        if mw_value:
            mw_dayparts.add(canonical_daypart(mw_value).casefold())
        else:
            normalized = canonical_propagation(item).casefold()
            if normalized:
                fm_nwr_modes.add(normalized)
    return mw_dayparts, fm_nwr_modes


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


def allowed_challenge_frequencies(
    challenge: dict[str, object], frequencies: list[float]
) -> list[float]:
    rules = challenge.get("rules", {})
    spec = rules.get("frequencies", "ALL") if isinstance(rules, dict) else "ALL"
    return [value for value in frequencies if frequency_allowed(spec, value)]


def load_challenges() -> list[dict[str, object]]:
    frame = pd.read_csv(CHALLENGE_FILE, dtype=str).fillna("")
    return challenges_from_frame(frame)


def challenges_from_frame(frame: pd.DataFrame) -> list[dict[str, object]]:
    challenges: list[dict[str, object]] = []
    for row in frame.to_dict("records"):
        if not _enabled(row.get("active", "true")):
            continue
        bands = ordered_band_options(row.get("bands", ""))
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
                "station_eligibility": _text(row.get("station_eligibility")) or "All stations",
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


def log_qualifies(
    log: pd.Series | dict[str, object], challenge: dict[str, object],
    *, season_logs: pd.DataFrame | None = None,
) -> bool:
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
    reception_value = pd.to_datetime(
        value.get("reception_utc"), utc=True, errors="coerce"
    )
    if pd.isna(reception_value):
        return False
    reception = reception_value.to_pydatetime()
    if not challenge["start_utc"] <= reception <= challenge["end_utc"]:
        return False
    rules = challenge["rules"]
    raw_propagation = value.get("propagation")
    band = str(value.get("band", "")).strip().upper()
    mw_dayparts, fm_nwr_modes = challenge_propagation_rules(rules)
    if band == "MW":
        if (
            mw_dayparts
            and canonical_daypart(raw_propagation).casefold() not in mw_dayparts
        ):
            return False
    elif (
        fm_nwr_modes
        and canonical_propagation(raw_propagation).casefold() not in fm_nwr_modes
    ):
        return False
    if new_season_stations_only(challenge):
        return bool(_new_season_reception_mask(pd.DataFrame([value]), challenge, season_logs).iloc[0])
    return True


def challenge_log_mask(
    logs: pd.DataFrame, challenge: dict[str, object],
    *, season_logs: pd.DataFrame | None = None,
) -> pd.Series:
    """Vectorized equivalent of ``log_qualifies`` for leaderboard-sized data."""
    if logs.empty:
        return pd.Series(False, index=logs.index, dtype=bool)
    mask = logs["band"].fillna("").astype(str).str.upper().isin(challenge["bands"])
    rules = challenge["rules"]

    frequencies = pd.to_numeric(logs["frequency"], errors="coerce")
    specification = rules.get("frequencies", "ALL")
    if specification != "ALL":
        frequency_mask = pd.Series(False, index=logs.index, dtype=bool)
        for item in specification if isinstance(specification, list) else []:
            if isinstance(item, tuple):
                frequency_mask |= frequencies.between(
                    float(item[0]) - 0.001, float(item[1]) + 0.001
                )
            else:
                frequency_mask |= (frequencies - float(item)).abs() < 0.001
        mask &= frequency_mask

    countries = logs["station_country"].fillna("").astype(str).str.strip().str.casefold()
    regions = logs["station_region"].fillna("").astype(str).str.strip().str.casefold()
    include_countries = {item.casefold() for item in rules.get("include_countries", [])}
    exclude_countries = {item.casefold() for item in rules.get("exclude_countries", [])}
    include_regions = {item.casefold() for item in rules.get("include_regions", [])}
    exclude_regions = {item.casefold() for item in rules.get("exclude_regions", [])}
    if include_countries:
        mask &= countries.isin(include_countries)
    if exclude_countries:
        mask &= ~countries.isin(exclude_countries)
    if include_regions:
        mask &= regions.isin(include_regions)
    if exclude_regions:
        mask &= ~regions.isin(exclude_regions)

    distances = pd.to_numeric(logs["distance_miles"], errors="coerce")
    if rules.get("min_distance") is not None:
        mask &= distances >= float(rules["min_distance"])
    if rules.get("max_distance") is not None:
        mask &= distances <= float(rules["max_distance"])

    receptions = pd.to_datetime(logs["reception_utc"], utc=True, errors="coerce", format="mixed")
    mask &= receptions.between(challenge["start_utc"], challenge["end_utc"])

    raw_propagation = logs["propagation"].fillna("")
    bands = logs["band"].fillna("").astype(str).str.strip().str.upper()
    mw_dayparts, fm_nwr_modes = challenge_propagation_rules(rules)
    if mw_dayparts:
        mask &= ~bands.eq("MW") | raw_propagation.map(
            canonical_daypart
        ).str.casefold().isin(mw_dayparts)
    if fm_nwr_modes:
        mask &= bands.eq("MW") | raw_propagation.map(
            canonical_propagation
        ).str.casefold().isin(fm_nwr_modes)
    if new_season_stations_only(challenge):
        mask &= _new_season_reception_mask(logs, challenge, season_logs)
    return mask.fillna(False)


def logs_qualifying_for_challenges(
    logs: pd.DataFrame, challenges: list[dict[str, object]],
    *, season_logs: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Return each reception once when it qualifies for at least one challenge."""
    if logs.empty or not challenges:
        return logs.iloc[0:0].copy()
    eligible = pd.Series(False, index=logs.index, dtype=bool)
    for challenge in challenges:
        eligible |= challenge_log_mask(logs, challenge, season_logs=season_logs)
    return logs[eligible].copy()


def validate_season_submission(
    log: pd.Series | dict[str, object],
    challenges: list[dict[str, object]],
    now: datetime | None = None,
    *, season_logs: pd.DataFrame | None = None,
) -> tuple[bool, str, list[str]]:
    """Validate one submitted reception and identify any sprint memberships.

    A reception is accepted only when it is not in the future and qualifies for at
    least one enabled marathon. Sprint membership is an additional classification,
    never a replacement for the season-long acceptance boundary.
    """
    instant = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    value = dict(log)
    parsed = pd.to_datetime(value.get("reception_utc"), utc=True, errors="coerce")
    if pd.isna(parsed):
        return False, "Reception date and time are invalid.", []
    reception = parsed.to_pydatetime()
    if reception > instant:
        return False, "Reception date and time cannot be in the future.", []

    marathons = [item for item in challenges if item.get("type") == "marathon"]
    if not marathons:
        return (
            False,
            "No enabled Season 7 marathon is configured, so reception entry is currently closed.",
            [],
        )
    qualifying_marathons = [
        item for item in marathons if log_qualifies(value, item)
    ]
    if not qualifying_marathons:
        band = _text(value.get("band")).upper() or "selected"
        return (
            False,
            f"This {band} reception is outside the enabled Season 7 marathon criteria and was not saved.",
            [],
        )
    sprint_history = (
        pd.concat([season_logs, pd.DataFrame([value])], ignore_index=True)
        if season_logs is not None else None
    )
    sprint_names = [
        str(item["name"])
        for item in challenges
        if item.get("type") == "sprint" and log_qualifies(value, item, season_logs=sprint_history)
    ]
    return True, "Reception is eligible for Season 7.", sprint_names


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
