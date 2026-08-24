from __future__ import annotations

import math
import re
from typing import Any


EARTH_RADIUS_MILES = 3958.8


def valid_coordinates(latitude: object, longitude: object) -> bool:
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        return False
    return math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180


def valid_grid(locator: object) -> bool:
    return bool(re.fullmatch(r"[A-R]{2}\d{2}(?:[A-X]{2})?", str(locator).strip().upper()))


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


def resolve_place(
    city: str,
    region: str,
    country: str,
    geocoder: Any,
) -> dict[str, object]:
    """Resolve a typed place and return validated coordinates plus its 6-character grid."""
    city = city.strip()
    region = region.strip()
    country = country.strip()
    query = ", ".join(value for value in (city, region, country) if value)
    if not query:
        raise ValueError("Enter a city, region, or country to search.")
    result = geocoder.geocode(query, exactly_one=True, addressdetails=True)
    if result is None:
        raise ValueError("That location could not be found. Try a grid or manual coordinates.")
    latitude = float(result.latitude)
    longitude = float(result.longitude)
    if not valid_coordinates(latitude, longitude):
        raise ValueError("The location service returned invalid coordinates. Try a grid or manual coordinates.")
    return {
        "city": city,
        "region": region,
        "country": country,
        "latitude": latitude,
        "longitude": longitude,
        "grid": latlon_to_grid(latitude, longitude),
        "display_name": str(getattr(result, "address", query) or query),
    }


def repair_geography(values: dict[str, object], geocoder: Any | None = None) -> dict[str, object]:
    """Fill missing coordinates/grid from existing coordinates, grid, or a place lookup."""
    latitude = values.get("latitude", "")
    longitude = values.get("longitude", "")
    grid = str(values.get("grid", "")).strip().upper()
    if valid_coordinates(latitude, longitude):
        return {
            "latitude": float(latitude),
            "longitude": float(longitude),
            "grid": grid if valid_grid(grid) else latlon_to_grid(float(latitude), float(longitude)),
        }
    if valid_grid(grid):
        latitude, longitude = grid_to_latlon(grid)
        return {"latitude": latitude, "longitude": longitude, "grid": grid}
    if geocoder is None:
        raise ValueError("This saved location needs a city lookup before it can be repaired.")
    return resolve_place(
        str(values.get("city", "")),
        str(values.get("region", "")),
        str(values.get("country", "")),
        geocoder,
    )
