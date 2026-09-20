from __future__ import annotations

import json
import math
import re
import unicodedata
from datetime import datetime, timezone
from functools import lru_cache

import pandas as pd

from dxcore.config import (
    COUNTRY_GEOJSON_FILE,
    COUNTY_OVERLAY_GEOJSON_FILE,
    COUNTY_REFERENCE_FILE,
)
from dxcore.metrics import add_geography_keys, normalize_county
from dxcore.subdivisions import add_subdivision_keys, north_america_admin1_geojson


HEARD_FILL = [0, 190, 230, 82]
UNHEARD_FILL = [86, 103, 120, 16]


def _token(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(character for character in text if not unicodedata.combining(character))
    return re.sub(r"[^a-z0-9]", "", text.casefold())


COUNTRY_CODE_ALIASES = {
    "antigua": "ATG",
    "bah": "BHS",
    "ber": "BMU",
    "bes": "BES",
    "bonaire": "BES",
    "canaryislands": "ESP",
    "ctr": "CRI",
    "djbouti": "DJI",
    "england": "GBR",
    "jmc": "JAM",
    "kampuchea": "KHM",
    "korea": "KOR",
    "laopdr": "LAO",
    "maldiveislands": "MDV",
    "ncg": "NIC",
    "northernireland": "GBR",
    "pnr": "PAN",
    "puertorico": "PRI",
    "sanandresyprovidencia": "COL",
    "sao tomeprincipe": "STP",
    "saotomeprincipe": "STP",
    "scn": "KNA",
    "southkorea": "KOR",
    "thenetherlands": "NLD",
    "uae": "ARE",
    "unitedkingdom": "GBR",
    "unitedstates": "USA",
    "unitedstatesofamerica": "USA",
    "usvirginislands": "VIR",
    "usa": "USA",
    "vrg": "VGB",
}


def _copy_feature(feature: dict[str, object], **properties: object) -> dict[str, object]:
    return {
        "type": "Feature",
        "geometry": feature.get("geometry", {}),
        "properties": {**feature.get("properties", {}), **properties},
    }


def _solar_position(moment: datetime) -> tuple[float, float]:
    """Return approximate subsolar latitude and longitude in degrees."""
    instant = moment.astimezone(timezone.utc)
    day = instant.timetuple().tm_yday
    hour = instant.hour + instant.minute / 60 + instant.second / 3600
    gamma = 2 * math.pi / 365 * (day - 1 + (hour - 12) / 24)
    equation_of_time = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma)
        - 0.040849 * math.sin(2 * gamma)
    )
    declination = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2 * gamma)
        + 0.000907 * math.sin(2 * gamma)
        - 0.002697 * math.cos(3 * gamma)
        + 0.00148 * math.sin(3 * gamma)
    )
    minutes = instant.hour * 60 + instant.minute + instant.second / 60
    longitude = (720 - minutes - equation_of_time) / 4
    longitude = ((longitude + 180) % 360) - 180
    return math.degrees(declination), longitude


@lru_cache(maxsize=12)
def _grayline_cells_for_minute(minute_key: str) -> tuple[dict[str, object], ...]:
    moment = datetime.fromisoformat(minute_key).replace(tzinfo=timezone.utc)
    solar_latitude, solar_longitude = _solar_position(moment)
    solar_latitude_radians = math.radians(solar_latitude)
    cells: list[dict[str, object]] = []
    colors = {
        "Daylight": [255, 244, 178, 34],
        "Grayline": [255, 156, 40, 88],
        "Darkness": [17, 30, 60, 96],
    }
    for latitude in range(-90, 90, 5):
        center_latitude = latitude + 2.5
        latitude_radians = math.radians(center_latitude)
        for longitude in range(-180, 180, 5):
            center_longitude = longitude + 2.5
            hour_angle = math.radians(center_longitude - solar_longitude)
            sine_altitude = (
                math.sin(latitude_radians) * math.sin(solar_latitude_radians)
                + math.cos(latitude_radians)
                * math.cos(solar_latitude_radians)
                * math.cos(hour_angle)
            )
            altitude = math.degrees(math.asin(max(-1.0, min(1.0, sine_altitude))))
            status = "Darkness" if altitude < -6 else "Daylight" if altitude > 6 else "Grayline"
            cells.append(
                {
                    "polygon": [
                        [longitude, latitude],
                        [longitude + 5, latitude],
                        [longitude + 5, latitude + 5],
                        [longitude, latitude + 5],
                        [longitude, latitude],
                    ],
                    "color": colors[status],
                    "status": status,
                }
            )
    return tuple(cells)


def grayline_cells(moment: datetime | None = None) -> tuple[list[dict[str, object]], datetime]:
    instant = (moment or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(
        second=0, microsecond=0
    )
    return list(_grayline_cells_for_minute(instant.replace(tzinfo=None).isoformat())), instant


def admin1_progress_geojson(logs: pd.DataFrame) -> tuple[dict[str, object], int]:
    source = north_america_admin1_geojson()
    aliases: dict[tuple[str, str], str] = {}
    for feature in source.get("features", []):
        properties = feature.get("properties", {})
        country = str(properties.get("adm0_a3", ""))
        code = str(properties.get("iso_3166_2", ""))
        for value in (
            code,
            properties.get("postal", ""),
            properties.get("name", ""),
            properties.get("name_en", ""),
        ):
            if _token(value):
                aliases[(country, _token(value))] = code

    heard_codes: set[str] = set()
    if not logs.empty:
        for row in logs.to_dict("records"):
            country = country_code(row.get("station_country", ""))
            code = aliases.get((country, _token(row.get("station_region", ""))), "")
            if code:
                heard_codes.add(code)
        for country in ("CAN", "MEX"):
            mapped = add_subdivision_keys(logs, country)
            for code in mapped.get("admin1_code", pd.Series(dtype=str)).astype(str):
                heard_codes.add("MX-DIF" if code == "MX-CMX" else code)

    features = []
    for feature in source.get("features", []):
        code = str(feature.get("properties", {}).get("iso_3166_2", ""))
        heard = code in heard_codes
        features.append(
            _copy_feature(
                feature,
                heard=heard,
                heard_label="Heard" if heard else "Unheard",
                fill_color=HEARD_FILL if heard else UNHEARD_FILL,
            )
        )
    return {"type": "FeatureCollection", "features": features}, len(heard_codes)


@lru_cache(maxsize=1)
def maidenhead_grid_lines() -> tuple[dict[str, object], ...]:
    lines = [
        {"path": [[longitude, -90], [longitude, 90]]}
        for longitude in range(-180, 181, 2)
    ]
    lines.extend(
        {"path": [[-180, latitude], [180, latitude]]}
        for latitude in range(-90, 91)
    )
    return tuple(lines)


def _grid_polygon(grid: str) -> list[list[float]] | None:
    text = str(grid).strip().upper()[:4]
    if not re.fullmatch(r"[A-R]{2}\d{2}", text):
        return None
    longitude = -180 + (ord(text[0]) - ord("A")) * 20 + int(text[2]) * 2
    latitude = -90 + (ord(text[1]) - ord("A")) * 10 + int(text[3])
    return [
        [longitude, latitude],
        [longitude + 2, latitude],
        [longitude + 2, latitude + 1],
        [longitude, latitude + 1],
        [longitude, latitude],
    ]


def heard_grid_polygons(logs: pd.DataFrame) -> tuple[list[dict[str, object]], int]:
    rows = add_geography_keys(logs) if not logs.empty else logs.copy()
    heard_grids = sorted(
        value for value in set(rows.get("grid4", pd.Series(dtype=str)).astype(str)) if value
    )
    polygons = [
        {"grid4": grid, "polygon": polygon, "color": HEARD_FILL}
        for grid in heard_grids
        if (polygon := _grid_polygon(grid)) is not None
    ]
    return polygons, len(polygons)


@lru_cache(maxsize=1)
def _county_assets() -> tuple[dict[str, object], dict[str, str]]:
    reference = pd.read_csv(COUNTY_REFERENCE_FILE, dtype=str).fillna("")
    key_lookup = {
        str(row["geoid"]): f"{str(row['state']).upper()}|{normalize_county(row['county'])}"
        for row in reference.to_dict("records")
    }
    with COUNTY_OVERLAY_GEOJSON_FILE.open(encoding="utf-8") as handle:
        geojson = json.load(handle)
    return geojson, key_lookup


def county_progress_geojson(logs: pd.DataFrame) -> tuple[dict[str, object], int]:
    source, key_lookup = _county_assets()
    rows = add_geography_keys(logs) if not logs.empty else logs.copy()
    heard_keys = {
        value
        for value in rows.get("county_key", pd.Series(dtype=str)).astype(str)
        if value
    }
    features = []
    heard_geoids: set[str] = set()
    for feature in source.get("features", []):
        geoid = str(feature.get("properties", {}).get("geoid", ""))
        heard = key_lookup.get(geoid, "") in heard_keys
        if heard:
            heard_geoids.add(geoid)
        features.append(
            _copy_feature(
                feature,
                heard=heard,
                heard_label="Heard" if heard else "Unheard",
                fill_color=HEARD_FILL if heard else UNHEARD_FILL,
            )
        )
    return {"type": "FeatureCollection", "features": features}, len(heard_geoids)


@lru_cache(maxsize=1)
def _country_asset() -> dict[str, object]:
    with COUNTRY_GEOJSON_FILE.open(encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache(maxsize=1)
def _country_aliases() -> dict[str, str]:
    aliases = dict(COUNTRY_CODE_ALIASES)
    for feature in _country_asset().get("features", []):
        properties = feature.get("properties", {})
        code = str(properties.get("MAP_CODE", properties.get("ADM0_A3", "")))
        for key in (
            "NAME",
            "NAME_LONG",
            "NAME_EN",
            "ISO_A2",
            "ISO_A3",
            "POSTAL",
            "BRK_NAME",
            "GEOUNIT",
            "GU_A3",
            "SU_A3",
            "MAP_CODE",
        ):
            token = _token(properties.get(key, ""))
            if token and code:
                aliases.setdefault(token, code)
        admin_code = str(properties.get("ADM0_A3", ""))
        for key in ("ADMIN", "SOVEREIGNT", "ADM0_A3"):
            token = _token(properties.get(key, ""))
            if token and admin_code:
                aliases.setdefault(token, admin_code)
    return aliases


def country_code(value: object) -> str:
    token = _token(value)
    return _country_aliases().get(token, COUNTRY_CODE_ALIASES.get(token, ""))


def country_progress_geojson(logs: pd.DataFrame) -> tuple[dict[str, object], int]:
    heard_codes = {
        code
        for code in logs.get("station_country", pd.Series(dtype=str)).map(country_code)
        if code
    }
    features = []
    matched: set[str] = set()
    for feature in _country_asset().get("features", []):
        properties = feature.get("properties", {})
        code = str(properties.get("MAP_CODE", properties.get("ADM0_A3", "")))
        heard = code in heard_codes
        if heard:
            matched.add(code)
        features.append(
            _copy_feature(
                feature,
                heard=heard,
                heard_label="Heard" if heard else "Unheard",
                fill_color=HEARD_FILL if heard else UNHEARD_FILL,
            )
        )
    return {"type": "FeatureCollection", "features": features}, len(matched)
