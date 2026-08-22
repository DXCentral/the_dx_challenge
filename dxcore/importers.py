from __future__ import annotations

import csv
import hashlib
import html
import io
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

from dxcore.geo import haversine_miles
from dxcore.solar import mw_propagation


MAX_IMPORT_ROWS = 50_000
NOT_MAPPED = "<Not mapped>"


@dataclass(frozen=True)
class ParsedUpload:
    frame: pd.DataFrame
    detected_format: str
    warnings: tuple[str, ...] = ()


PRESET_MAPPINGS: dict[str, dict[str, str]] = {
    "MWList": {
        "frequency": "kHz",
        "call": "Program",
        "date": "Date",
        "time": "UTC",
        "city": "Location",
        "region": "Reg",
        "country": "ITU",
        "propagation": "Propa",
        "notes": "Remarks",
    },
    "FMList": {
        "frequency": "MHz",
        "call": "Program",
        "date": "Date",
        "time": "UTC",
        "city": "Location",
        "region": "Reg",
        "country": "ITU",
        "propagation": "Propa",
        "notes": "Remarks",
    },
    "WLogger": {
        "frequency": "Frequency",
        "call": "Callsign",
        "timestamp": "Timestamp",
        "city": "City",
        "region": "State",
        "country": "Country",
        "propagation": "Mode",
        "notes": "Comments",
        "distance": "Distance",
    },
}


FIELD_SUGGESTIONS: dict[str, tuple[str, ...]] = {
    "band": ("band",),
    "frequency": ("frequency", "freq", "mhz", "khz"),
    "call": ("callsign", "call sign", "call", "station", "program"),
    "timestamp": ("timestamp", "date time", "datetime", "utc helper"),
    "date": ("utc date", "date of reception", "reception date", "date"),
    "time": ("utc time", "time of reception", "reception time", "time", "utc"),
    "city": ("city of license", "station city", "location", "city"),
    "region": ("state/province", "state or prov", "us state/canadian prov", "station state", "state", "reg"),
    "country": ("station country", "country", "itu"),
    "county": ("county/parish", "county", "parish"),
    "grid": ("grid square", "gridsquare", "grid"),
    "propagation": ("propagation", "propa", "mode", "time of day"),
    "notes": ("comments", "remarks", "details", "notes"),
    "is_sdr": ("received using an sdr", "sdr used", "sdr"),
    "is_portable": ("portable operation", "portable", "rover"),
}


def _decode(raw: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise ValueError("The uploaded text file could not be decoded.")


def _detect_delimiter(line: str) -> str:
    counts = {delimiter: line.count(delimiter) for delimiter in (";", ",", "\t")}
    return max(counts, key=counts.get)


def _header_score(line: str) -> int:
    lowered = line.casefold()
    markers = [
        "frequency", "freq", "khz", "mhz", "program", "station", "call",
        "date", "utc", "timestamp", "city", "state", "mode", "propa",
    ]
    return sum(marker in lowered for marker in markers)


def _read_delimited(raw: bytes) -> tuple[pd.DataFrame, list[str]]:
    text, encoding = _decode(raw)
    lines = text.splitlines()
    if not lines:
        raise ValueError("The uploaded file is empty.")
    candidates = [(index, _header_score(line)) for index, line in enumerate(lines[:50])]
    header_index, score = max(candidates, key=lambda item: item[1])
    if score < 2:
        header_index = max(
            range(min(50, len(lines))),
            key=lambda index: max(lines[index].count(";"), lines[index].count(","), lines[index].count("\t")),
        )
    delimiter = _detect_delimiter(lines[header_index])
    quoting = csv.QUOTE_NONE if delimiter == ";" else csv.QUOTE_MINIMAL
    headers = [
        value.strip(" \t\"'")
        for value in next(csv.reader([lines[header_index]], delimiter=delimiter, quoting=quoting))
    ]
    if not any(headers):
        raise ValueError("A usable header row could not be found.")
    unique_headers: list[str] = []
    for index, header in enumerate(headers):
        candidate = header or f"Unnamed {index + 1}"
        while candidate in unique_headers:
            candidate = f"{header or 'Unnamed'} {index + 1}"
        unique_headers.append(candidate)

    rows: list[list[str]] = []
    malformed = 0
    for raw_line in lines[header_index + 1 :]:
        if not raw_line.strip():
            continue
        # MWList encodes quotes as &quot;; decode before separating fields so
        # the entity semicolon is never mistaken for a delimiter.
        values = next(
            csv.reader([html.unescape(raw_line)], delimiter=delimiter, quoting=quoting)
        )
        if len(values) == len(unique_headers) + 1 and values[-1] == "":
            values.pop()
        if len(values) != len(unique_headers):
            malformed += 1
            continue
        rows.append([value.strip(" \t\"'") for value in values])
        if len(rows) > MAX_IMPORT_ROWS:
            raise ValueError(f"Imports are limited to {MAX_IMPORT_ROWS:,} rows per file.")
    warnings = [f"Decoded as {encoding}."]
    if header_index:
        warnings.append(f"Ignored {header_index:,} descriptive line(s) before the table header.")
    if malformed:
        warnings.append(f"Held back {malformed:,} structurally malformed row(s).")
    return pd.DataFrame(rows, columns=unique_headers, dtype=str).fillna(""), warnings


def detect_source_format(columns: Iterable[object]) -> str:
    lowered = {str(column).strip().casefold() for column in columns}
    if {"date", "utc", "khz", "program"}.issubset(lowered):
        return "MWList"
    if {"date", "utc", "mhz", "program"}.issubset(lowered):
        return "FMList"
    if (
        any("timestamp" in column for column in lowered)
        and any(column in lowered for column in ("mode", "propagation"))
        and any(column in lowered for column in ("callsign", "call", "station"))
    ):
        return "WLogger"
    return "Custom"


def read_upload(file_name: str, raw: bytes) -> ParsedUpload:
    suffix = Path(file_name).suffix.casefold()
    if suffix == ".xlsx":
        try:
            frame = pd.read_excel(io.BytesIO(raw), dtype=str).fillna("")
        except ImportError as error:
            raise ValueError("XLSX support is unavailable on this deployment.") from error
        warnings = ["Read the first worksheet from the XLSX file."]
    elif suffix in {".csv", ".tsv", ".txt"}:
        frame, warnings = _read_delimited(raw)
    else:
        raise ValueError("Upload a CSV, TSV, TXT, or XLSX file.")
    if frame.empty:
        raise ValueError("The uploaded file contains no data rows.")
    if len(frame) > MAX_IMPORT_ROWS:
        raise ValueError(f"Imports are limited to {MAX_IMPORT_ROWS:,} rows per file.")
    frame.columns = [str(column).strip() for column in frame.columns]
    return ParsedUpload(frame=frame, detected_format=detect_source_format(frame.columns), warnings=tuple(warnings))


def suggest_mapping(columns: Iterable[object]) -> dict[str, str]:
    names = [str(column) for column in columns]
    result: dict[str, str] = {}
    for field, guesses in FIELD_SUGGESTIONS.items():
        exact = next(
            (name for guess in guesses for name in names if name.strip().casefold() == guess),
            None,
        )
        partial = next(
            (name for guess in guesses for name in names if guess in name.strip().casefold()),
            None,
        )
        result[field] = exact or partial or NOT_MAPPED
    return result


def mapping_for_format(source_format: str, columns: Iterable[object]) -> dict[str, str]:
    suggested = suggest_mapping(columns)
    for field, column in PRESET_MAPPINGS.get(source_format, {}).items():
        if column in columns:
            suggested[field] = column
    return suggested


def _ascii(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode().strip()


def normalize_token(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", _ascii(value).upper())


def normalize_call(value: object) -> str:
    text = _ascii(value).upper().strip()
    text = re.sub(r"\s+R:.*$", "", text)
    text = re.sub(r"(?:-FM|\s+FM)\b", "", text)
    text = re.sub(r"-?HD\d*\b", "", text)
    return normalize_token(text)


NETWORK_ALIASES = {
    "REBELDE": "RADIOREBELDE",
    "RREBELDE": "RADIOREBELDE",
    "RELOJ": "RADIORELOJ",
    "RRELOJ": "RADIORELOJ",
    "PROGRESO": "RADIOPROGRESO",
    "RPROGRESO": "RADIOPROGRESO",
    "ENCICLOPEDIA": "RADIOENCICLOPEDIA",
    "RENCICLOPEDIA": "RADIOENCICLOPEDIA",
    "CMBF": "RADIOMUSICALNACIONAL",
}


def _station_alias(value: object) -> str:
    token = normalize_token(value)
    frequency_free = re.sub(r"\d+$", "", token)
    for alias, canonical in NETWORK_ALIASES.items():
        if alias in frequency_free:
            return canonical
    return frequency_free


def _value(row: pd.Series, mapping: dict[str, str], field: str) -> object:
    column = mapping.get(field, NOT_MAPPED)
    return row.get(column, "") if column and column != NOT_MAPPED else ""


def _parse_date(value: object, date_order: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    formats = {
        "DMY": ("%d.%m.%y", "%d.%m.%Y", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y"),
        "MDY": ("%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%m-%d-%y"),
        "YMD": ("%Y-%m-%d", "%Y/%m/%d"),
    }
    for pattern in formats.get(date_order, formats["MDY"]):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    # ISO is unambiguous and accepted under every user-selected protocol.
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError as error:
        raise ValueError(f"Unrecognized date: {text}") from error


def _parse_time(value: object) -> time:
    if isinstance(value, datetime):
        return value.time().replace(tzinfo=None)
    if isinstance(value, time):
        return value.replace(tzinfo=None)
    text = str(value).strip()
    if re.fullmatch(r"\d{1,4}", text):
        text = text.zfill(4)
        hour, minute = int(text[:2]), int(text[2:])
        if hour <= 23 and minute <= 59:
            return time(hour, minute)
    for pattern in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M:%S %p"):
        try:
            return datetime.strptime(text, pattern).time()
        except ValueError:
            continue
    raise ValueError(f"Unrecognized time: {text}")


def parse_reception(
    row: pd.Series,
    mapping: dict[str, str],
    *,
    date_order: str,
    time_protocol: str,
    timezone_name: str,
) -> datetime:
    timestamp_value = _value(row, mapping, "timestamp")
    if str(timestamp_value).strip():
        if isinstance(timestamp_value, pd.Timestamp):
            local = timestamp_value.to_pydatetime()
        elif isinstance(timestamp_value, datetime):
            local = timestamp_value
        else:
            text = str(timestamp_value).strip()
            parsed = None
            for separator in (" ", "T"):
                if separator not in text:
                    continue
                date_text, time_text = text.split(separator, 1)
                try:
                    parsed = datetime.combine(
                        _parse_date(date_text, date_order),
                        _parse_time(time_text.replace("Z", "").strip()),
                    )
                    break
                except ValueError:
                    continue
            if parsed is None:
                raise ValueError(f"Unrecognized timestamp: {text}")
            local = parsed
    else:
        local = datetime.combine(
            _parse_date(_value(row, mapping, "date"), date_order),
            _parse_time(_value(row, mapping, "time")),
        )
    if local.tzinfo is not None:
        return local.astimezone(timezone.utc).replace(microsecond=0)
    if time_protocol == "UTC":
        return local.replace(tzinfo=timezone.utc, microsecond=0)
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as error:
        raise ValueError(f"Unknown IANA time zone: {timezone_name}") from error
    return local.replace(tzinfo=zone, microsecond=0).astimezone(timezone.utc)


def _band(value: object, frequency: float, fixed_band: str) -> str:
    token = normalize_token(value or fixed_band)
    aliases = {"AM": "MW", "MEDIUMWAVE": "MW", "WEATHER": "NWR", "NOAA": "NWR"}
    token = aliases.get(token, token)
    if token in {"MW", "FM", "NWR"}:
        return token
    if 530 <= frequency <= 1710:
        return "MW"
    if 87.0 <= frequency <= 108.0:
        return "FM"
    if 162.4 <= frequency <= 162.55:
        return "NWR"
    raise ValueError("Frequency is outside the supported MW, FM, and NWR bands.")


def _frequency(value: object) -> float:
    text = str(value).strip().replace(" ", "").replace(",", ".")
    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        raise ValueError(f"Invalid frequency: {value}")
    return float(match.group())


def _bool(value: object, default: bool) -> bool:
    text = normalize_token(value)
    if not text:
        return default
    if text in {"1", "Y", "YES", "TRUE", "SDR", "PORTABLE", "ROVER"}:
        return True
    if text in {"0", "N", "NO", "FALSE", "NONE"}:
        return False
    return default


def normalize_propagation(value: object, band: str) -> str:
    token = normalize_token(value)
    if band == "MW":
        return "Other"
    aliases = {
        "ES": "Sporadic E",
        "SPORADICE": "Sporadic E",
        "SPORADICES": "Sporadic E",
        "TR": "Tropo",
        "TROPO": "Tropo",
        "TROPOSPHERIC": "Tropo",
        "MS": "Meteor Scatter",
        "METEORSCATTER": "Meteor Scatter",
        "AU": "Aurora",
        "AURORA": "Aurora",
        "AS": "Aircraft Scatter",
        "AIRCRAFTSCATTER": "Aircraft Scatter",
        "LOS": "Local",
        "LOCAL": "Local",
    }
    return aliases.get(token, "Other")


def _match_station(
    identity_index: dict[tuple[str, float, str], list[dict[str, object]]],
    station_frequencies: set[tuple[str, float]],
    *,
    band: str,
    frequency: float,
    source_call: object,
    city: object,
    region: object,
    country: object,
) -> tuple[dict[str, object] | None, str]:
    frequency_key = (band, round(frequency, 3))
    if frequency_key not in station_frequencies:
        return None, "No station-list record exists on this frequency."
    source_normal = normalize_call(source_call)
    source_alias = _station_alias(source_call)
    city_normal = normalize_token(city)
    region_normal = normalize_token(region)
    country_normal = normalize_token(country)

    identities = {source_normal, f"ALIAS:{source_alias}"}
    identities.update(
        normalize_call(token)
        for token in re.findall(r"[A-Za-z0-9-]{3,}", _ascii(source_call))
    )
    candidates_by_id: dict[str, dict[str, object]] = {}
    for identity in identities:
        for candidate in identity_index.get((*frequency_key, identity), []):
            candidates_by_id[str(candidate["station_id"])] = candidate

    scored: list[tuple[int, str, dict[str, object]]] = []
    for candidate in candidates_by_id.values():
        candidate_call = normalize_call(candidate["call"])
        candidate_alias = _station_alias(candidate["call"])
        score = 0
        if source_normal and source_normal == candidate_call:
            score = 120
        elif source_normal and len(candidate_call) >= 3 and source_normal.startswith(candidate_call):
            score = 110
        elif candidate_call and candidate_call in {
            normalize_call(token)
            for token in re.findall(r"[A-Za-z0-9-]{3,}", _ascii(source_call))
        }:
            score = 115
        elif source_alias and source_alias == candidate_alias:
            score = 100
        if not score:
            continue
        if region_normal and region_normal == normalize_token(candidate["region"]):
            score += 12
        if city_normal and city_normal == normalize_token(candidate["city"]):
            score += 10
        if country_normal and country_normal in {
            normalize_token(candidate["country"]),
            normalize_token(str(candidate["country"])[:3]),
        }:
            score += 6
        scored.append((score, str(candidate["station_id"]), candidate))
    if not scored:
        return None, "No exact station identity match; held for review instead of guessing."
    scored.sort(key=lambda item: item[0], reverse=True)
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        return None, "More than one station-list record matches; held for review."
    return scored[0][2], "Matched to the canonical station list."


def _notes(row: pd.Series, mapping: dict[str, str], source_format: str) -> str:
    parts: list[str] = []
    mapped = str(_value(row, mapping, "notes")).strip()
    if mapped:
        parts.append(mapped)
    if source_format in {"FMList", "MWList"}:
        for column in ("Details", "Remarks"):
            value = str(row.get(column, "")).strip()
            if value and value not in parts:
                parts.append(value)
    return " | ".join(parts)


def normalize_import(
    frame: pd.DataFrame,
    *,
    source_format: str,
    mapping: dict[str, str],
    date_order: str,
    time_protocol: str,
    timezone_name: str,
    fixed_band: str,
    default_propagation: str,
    default_is_sdr: bool,
    default_is_portable: bool,
    user_id: str,
    location: dict[str, object],
    stations: pd.DataFrame,
    existing_logs: pd.DataFrame,
    unlocked_bands: set[str],
) -> pd.DataFrame:
    results: list[dict[str, object]] = []
    identity_index: dict[tuple[str, float, str], list[dict[str, object]]] = {}
    station_frequencies: set[tuple[str, float]] = set()
    for station in stations.to_dict("records"):
        frequency_key = (str(station["band"]), round(float(station["frequency"]), 3))
        station_frequencies.add(frequency_key)
        for identity in {
            normalize_call(station["call"]),
            f"ALIAS:{_station_alias(station['call'])}",
        }:
            identity_index.setdefault((*frequency_key, identity), []).append(station)
    existing_times: dict[str, list[datetime]] = {}
    if not existing_logs.empty:
        for station_id, group in existing_logs.groupby("station_id"):
            existing_times[str(station_id)] = [
                value.to_pydatetime()
                for value in pd.to_datetime(group["reception_utc"], utc=True, errors="coerce").dropna()
            ]
    batch_times: dict[str, list[datetime]] = {}

    effective_date_order = "DMY" if source_format in {"FMList", "MWList"} else date_order
    effective_time_protocol = "UTC" if source_format in {"FMList", "MWList"} else time_protocol
    source_label = f"import_{source_format.casefold().replace(' ', '_')}"

    for source_row, (_, row) in enumerate(frame.iterrows(), 1):
        base: dict[str, object] = {
            "selected": False,
            "source_row": source_row,
            "status": "Invalid",
            "message": "",
            "source": source_label,
        }
        try:
            frequency = _frequency(_value(row, mapping, "frequency"))
            band = _band(_value(row, mapping, "band"), frequency, fixed_band)
            reception = parse_reception(
                row,
                mapping,
                date_order=effective_date_order,
                time_protocol=effective_time_protocol,
                timezone_name=timezone_name,
            )
            source_call = _value(row, mapping, "call")
            if not str(source_call).strip():
                raise ValueError("Station/call field is blank.")
            station, match_message = _match_station(
                identity_index,
                station_frequencies,
                band=band,
                frequency=frequency,
                source_call=source_call,
                city=_value(row, mapping, "city"),
                region=_value(row, mapping, "region"),
                country=_value(row, mapping, "country"),
            )
            if station is None:
                base.update(
                    {
                        "band": band,
                        "frequency": frequency,
                        "source_station": str(source_call),
                        "reception_utc": reception.isoformat(),
                        "status": "Needs review",
                        "message": match_message,
                    }
                )
                results.append(base)
                continue
            station_id = str(station["station_id"])
            if band not in unlocked_bands:
                status = "Bandscan locked"
                message = f"Complete the {band} bandscan at this QTH before importing."
            else:
                candidates = existing_times.get(station_id, []) + batch_times.get(station_id, [])
                duplicate = next(
                    (value for value in candidates if abs((reception - value).total_seconds()) <= 300),
                    None,
                )
                if duplicate is not None:
                    status = "Duplicate"
                    message = f"Same station is already present within five minutes of {duplicate:%Y-%m-%d %H:%M UTC}."
                else:
                    status = "Ready"
                    message = match_message
                    batch_times.setdefault(station_id, []).append(reception)

            if band == "MW":
                propagation = mw_propagation(
                    reception,
                    float(location["latitude"]),
                    float(location["longitude"]),
                )
            else:
                raw_prop = _value(row, mapping, "propagation") or default_propagation
                propagation = normalize_propagation(raw_prop, band)
            distance = round(
                haversine_miles(
                    float(location["latitude"]),
                    float(location["longitude"]),
                    float(station["latitude"]),
                    float(station["longitude"]),
                ),
                1,
            )
            base.update(
                {
                    "selected": status == "Ready",
                    "status": status,
                    "message": message,
                    "user_id": user_id,
                    "location_id": str(location["location_id"]),
                    "station_id": station_id,
                    "band": band,
                    "frequency": float(station["frequency"]),
                    "source_station": str(source_call),
                    "call": str(station["call"]),
                    "station_city": str(station["city"]),
                    "station_region": str(station["region"]),
                    "station_country": str(station["country"]),
                    "station_county": str(station["county"]),
                    "station_grid": str(station["grid"]),
                    "station_latitude": float(station["latitude"]),
                    "station_longitude": float(station["longitude"]),
                    "reception_utc": reception.isoformat(),
                    "distance_miles": distance,
                    "propagation": propagation,
                    "is_sdr": int(_bool(_value(row, mapping, "is_sdr"), default_is_sdr)),
                    "is_portable": int(_bool(_value(row, mapping, "is_portable"), default_is_portable)),
                    "notes": _notes(row, mapping, source_format),
                }
            )
        except (TypeError, ValueError, OverflowError) as error:
            base["message"] = str(error)
        results.append(base)

    return pd.DataFrame(results)


def import_batch_id(user_id: str, file_name: str, instant: datetime | None = None) -> str:
    now = instant or datetime.now(timezone.utc)
    raw = f"{user_id}|{file_name}|{now.isoformat()}".encode()
    return f"batch_{hashlib.sha1(raw).hexdigest()[:20]}"


def log_payloads(review: pd.DataFrame, batch_id: str) -> list[dict[str, object]]:
    fields = [
        "user_id", "location_id", "station_id", "band", "frequency", "call",
        "station_city", "station_region", "station_country", "station_county",
        "station_grid", "station_latitude", "station_longitude", "reception_utc",
        "distance_miles", "propagation", "is_sdr", "is_portable", "notes", "source",
    ]
    payloads: list[dict[str, object]] = []
    for row in review[(review["status"] == "Ready") & review["selected"].astype(bool)].to_dict("records"):
        payload = {field: row.get(field, "") for field in fields}
        payload["import_batch_id"] = batch_id
        payloads.append(payload)
    return payloads
