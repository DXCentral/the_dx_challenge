from __future__ import annotations

import math
import re


EARTH_RADIUS_MILES = 3958.8


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(float(lat1)), math.radians(float(lat2))
    delta_phi = math.radians(float(lat2) - float(lat1))
    delta_lambda = math.radians(float(lon2) - float(lon1))
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return EARTH_RADIUS_MILES * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def grid_to_latlon(locator: str) -> tuple[float, float]:
    """Return the center of a 4- or 6-character Maidenhead locator."""
    locator = locator.strip().upper()
    if not re.fullmatch(r"[A-R]{2}\d{2}(?:[A-X]{2})?", locator):
        raise ValueError("Enter a valid 4- or 6-character Maidenhead grid.")

    lon = (ord(locator[0]) - ord("A")) * 20 - 180
    lat = (ord(locator[1]) - ord("A")) * 10 - 90
    lon += int(locator[2]) * 2
    lat += int(locator[3])

    if len(locator) == 6:
        lon += (ord(locator[4]) - ord("A")) * (2 / 24) + (1 / 24)
        lat += (ord(locator[5]) - ord("A")) * (1 / 24) + (1 / 48)
    else:
        lon += 1
        lat += 0.5
    return round(lat, 6), round(lon, 6)


def latlon_to_grid(latitude: float, longitude: float, precision: int = 6) -> str:
    if precision not in {4, 6}:
        raise ValueError("Grid precision must be 4 or 6 characters.")
    lat = min(max(float(latitude), -90), 89.999999) + 90
    lon = min(max(float(longitude), -180), 179.999999) + 180
    field_lon = int(lon // 20)
    field_lat = int(lat // 10)
    lon -= field_lon * 20
    lat -= field_lat * 10
    square_lon = int(lon // 2)
    square_lat = int(lat)
    result = f"{chr(65 + field_lon)}{chr(65 + field_lat)}{square_lon}{square_lat}"
    if precision == 6:
        lon -= square_lon * 2
        lat -= square_lat
        sub_lon = min(23, int(lon / (2 / 24)))
        sub_lat = min(23, int(lat / (1 / 24)))
        result += f"{chr(65 + sub_lon)}{chr(65 + sub_lat)}"
    return result

