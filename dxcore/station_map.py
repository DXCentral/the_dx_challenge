from __future__ import annotations

import base64
import json
import math
import re
import struct
import unicodedata
import zlib
from datetime import datetime, timezone
from functools import lru_cache

import numpy as np
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


def _png_data_uri(rgba: np.ndarray) -> str:
    """Encode an RGBA array as a dependency-free PNG data URI."""
    height, width, channels = rgba.shape
    if channels != 4:
        raise ValueError("Grayline raster must contain RGBA pixels")

    def chunk(kind: bytes, payload: bytes) -> bytes:
        checksum = zlib.crc32(kind + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)

    scanlines = b"".join(b"\x00" + rgba[row].tobytes() for row in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(scanlines, level=9))
        + chunk(b"IEND", b"")
    )
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def _grayline_raster(solar_latitude: float, solar_longitude: float) -> str:
    """Build smooth day, civil-twilight, and night shading at 0.5-degree resolution."""
    latitudes = np.radians(np.linspace(89.75, -89.75, 360, dtype=np.float64))[:, None]
    longitudes = np.radians(np.linspace(-179.75, 179.75, 720, dtype=np.float64))[None, :]
    solar_latitude_radians = math.radians(solar_latitude)
    hour_angle = longitudes - math.radians(solar_longitude)
    sine_altitude = (
        np.sin(latitudes) * math.sin(solar_latitude_radians)
        + np.cos(latitudes) * math.cos(solar_latitude_radians) * np.cos(hour_angle)
    )
    altitude = np.degrees(np.arcsin(np.clip(sine_altitude, -1.0, 1.0)))

    daylight = np.array([255.0, 244.0, 178.0, 28.0])
    twilight = np.array([255.0, 156.0, 40.0, 92.0])
    darkness = np.array([17.0, 30.0, 60.0, 104.0])
    rgba = np.empty((*altitude.shape, 4), dtype=np.float64)

    night_mix = np.clip((altitude + 6.0) / 6.0, 0.0, 1.0)[..., None]
    day_mix = np.clip(altitude / 6.0, 0.0, 1.0)[..., None]
    rgba[:] = darkness
    night_to_twilight = altitude >= -6.0
    rgba[night_to_twilight] = (
        darkness + (twilight - darkness) * night_mix
    )[night_to_twilight]
    twilight_to_day = altitude >= 0.0
    rgba[twilight_to_day] = (
        twilight + (daylight - twilight) * day_mix
    )[twilight_to_day]
    return _png_data_uri(np.rint(rgba).astype(np.uint8))


def _terminator_paths(
    solar_latitude: float, solar_longitude: float
) -> tuple[dict[str, object], ...]:
    """Return a smooth great-circle solar terminator split safely at the date line."""
    latitude = math.radians(solar_latitude)
    longitude = math.radians(solar_longitude)
    sun = np.array(
        [
            math.cos(latitude) * math.cos(longitude),
            math.cos(latitude) * math.sin(longitude),
            math.sin(latitude),
        ]
    )
    reference = np.array([0.0, 0.0, 1.0])
    first_axis = np.cross(sun, reference)
    if np.linalg.norm(first_axis) < 1e-9:
        reference = np.array([0.0, 1.0, 0.0])
        first_axis = np.cross(sun, reference)
    first_axis /= np.linalg.norm(first_axis)
    second_axis = np.cross(sun, first_axis)

    segments: list[dict[str, object]] = []
    segment: list[list[float]] = []
    for angle in np.linspace(0.0, 2.0 * math.pi, 721):
        point = first_axis * math.cos(angle) + second_axis * math.sin(angle)
        point_longitude = math.degrees(math.atan2(point[1], point[0]))
        point_latitude = math.degrees(math.asin(float(np.clip(point[2], -1.0, 1.0))))
        coordinate = [point_longitude, point_latitude]
        if segment and abs(point_longitude - segment[-1][0]) > 180.0:
            if len(segment) > 1:
                segments.append({"path": segment})
            segment = [coordinate]
        else:
            segment.append(coordinate)
    if len(segment) > 1:
        segments.append({"path": segment})
    return tuple(segments)


@lru_cache(maxsize=12)
def _grayline_overlay_for_minute(
    minute_key: str,
) -> tuple[str, tuple[dict[str, object], ...]]:
    moment = datetime.fromisoformat(minute_key).replace(tzinfo=timezone.utc)
    solar_latitude, solar_longitude = _solar_position(moment)
    return (
        _grayline_raster(solar_latitude, solar_longitude),
        _terminator_paths(solar_latitude, solar_longitude),
    )


def grayline_overlay(
    moment: datetime | None = None,
) -> tuple[str, list[dict[str, object]], datetime]:
    instant = (moment or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(
        second=0, microsecond=0
    )
    image, paths = _grayline_overlay_for_minute(
        instant.replace(tzinfo=None).isoformat()
    )
    return image, list(paths), instant


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
