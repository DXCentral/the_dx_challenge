from __future__ import annotations

import hashlib
import re
from functools import lru_cache

import numpy as np
import pandas as pd

from dxcore.config import STATION_FILES
from dxcore.geo import EARTH_RADIUS_MILES, latlon_to_grid


MW_10_KHZ = [float(value) for value in range(530, 1720, 10)]
MW_9_KHZ = [float(value) for value in range(531, 1711, 9)]
FM_FREQUENCIES = [round(value / 10, 1) for value in range(881, 1080, 2)]
NWR_FREQUENCIES = [162.400, 162.425, 162.450, 162.475, 162.500, 162.525, 162.550]


def _text(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _location_key(city: object, region: object) -> str:
    return "|".join(
        re.sub(r"[^A-Z0-9]", "", _text(value).upper()) for value in (city, region)
    )


def _station_id(band: str, frequency: float, call: str, city: str, region: str, country: str) -> str:
    raw = "|".join([band, f"{frequency:.3f}", call.upper(), city.upper(), region.upper(), country.upper()])
    return f"{band.lower()}_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]}"


def _finalize(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame["frequency"] = pd.to_numeric(frame["frequency"], errors="coerce")
    frame["latitude"] = pd.to_numeric(frame["latitude"], errors="coerce")
    frame["longitude"] = pd.to_numeric(frame["longitude"], errors="coerce")
    frame = frame.dropna(subset=["frequency", "latitude", "longitude"])
    for column in ["call", "city", "region", "country", "county"]:
        frame[column] = frame[column].map(_text)
    frame["grid"] = [
        latlon_to_grid(lat, lon) for lat, lon in zip(frame["latitude"], frame["longitude"], strict=False)
    ]
    frame["station_id"] = [
        _station_id(band, freq, call, city, region, country)
        for band, freq, call, city, region, country in zip(
            frame["band"],
            frame["frequency"],
            frame["call"],
            frame["city"],
            frame["region"],
            frame["country"],
            strict=False,
        )
    ]
    return frame[
        [
            "station_id",
            "band",
            "frequency",
            "call",
            "city",
            "region",
            "country",
            "county",
            "grid",
            "latitude",
            "longitude",
        ]
    ].drop_duplicates("station_id")


@lru_cache(maxsize=1)
def load_stations() -> pd.DataFrame:
    mw = pd.read_csv(STATION_FILES["mw"], dtype=str).fillna("")
    mw_frame = pd.DataFrame(
        {
            "band": "MW",
            "frequency": mw["FREQ"],
            "call": mw["CALL"],
            "city": mw["CITY"],
            "region": mw["STATE"],
            "country": "United States",
            "county": mw.get("County", ""),
            "latitude": mw["LAT"],
            "longitude": mw["LON"],
        }
    )

    international = pd.read_csv(STATION_FILES["mw_international"], dtype=str).fillna("")
    international_frame = pd.DataFrame(
        {
            "band": "MW",
            "frequency": international["Frequency"],
            "call": international["Station Call Letters"],
            "city": international["Station City"],
            "region": international["Station State/Province"],
            "country": international["Station Country"],
            "county": "",
            "latitude": international["Station Lat"],
            "longitude": international["Station Long"],
        }
    )

    fm = pd.read_csv(STATION_FILES["fm"], dtype=str).fillna("")
    fm_frame = pd.DataFrame(
        {
            "band": "FM",
            "frequency": fm["Frequency"],
            "call": fm["Callsign"],
            "city": fm["City"],
            "region": fm["S/P"],
            "country": fm["Country"].replace({"USA": "United States"}),
            "county": fm.get("County", ""),
            "latitude": fm["Decimal_Lat"],
            "longitude": fm["Decimal_Lon"],
        }
    )

    # The NWR source's COUNTY field lists its entire warning-coverage area,
    # not the transmitter site's county. Resolve only from matching station
    # city/state records in the domestic MW/FM data; leave uncertain sites
    # blank instead of publishing a misleading coverage county.
    county_reference = pd.concat(
        [
            mw_frame[["city", "region", "county"]],
            fm_frame[["city", "region", "county"]],
        ],
        ignore_index=True,
    )
    county_reference = county_reference[county_reference["county"].map(_text) != ""].copy()
    county_reference["location_key"] = [
        _location_key(city, region)
        for city, region in zip(county_reference["city"], county_reference["region"], strict=False)
    ]
    county_lookup = (
        county_reference.groupby("location_key")["county"]
        .agg(lambda values: values.map(_text).value_counts().index[0])
        .to_dict()
    )

    nwr = pd.read_csv(STATION_FILES["nwr"], dtype=str).fillna("")
    nwr_frame = pd.DataFrame(
        {
            "band": "NWR",
            "frequency": nwr["FREQ"],
            "call": nwr["CALLSIGN"],
            "city": nwr["SITELOC"],
            "region": nwr["ST"],
            "country": "United States",
            "county": [
                county_lookup.get(_location_key(city, region), "")
                for city, region in zip(nwr["SITELOC"], nwr["ST"], strict=False)
            ],
            "latitude": nwr["LAT"],
            "longitude": nwr["LON"],
        }
    )
    return _finalize(pd.concat([mw_frame, international_frame, fm_frame, nwr_frame], ignore_index=True))


def frequencies_for_band(band: str, mw_spacing: str = "10 kHz") -> list[float]:
    if band == "MW":
        return MW_9_KHZ if mw_spacing == "9 kHz" else MW_10_KHZ
    if band == "FM":
        return FM_FREQUENCIES
    return NWR_FREQUENCIES


def with_distances(frame: pd.DataFrame, latitude: float, longitude: float) -> pd.DataFrame:
    if frame.empty:
        return frame.assign(distance_miles=pd.Series(dtype=float))
    lat1 = np.radians(float(latitude))
    lon1 = np.radians(float(longitude))
    lat2 = np.radians(frame["latitude"].astype(float).to_numpy())
    lon2 = np.radians(frame["longitude"].astype(float).to_numpy())
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    value = np.sin(delta_lat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(delta_lon / 2) ** 2
    distance = EARTH_RADIUS_MILES * 2 * np.arctan2(np.sqrt(value), np.sqrt(1 - value))
    result = frame.copy()
    result["distance_miles"] = np.round(distance, 1)
    return result.sort_values(["distance_miles", "call"])


def stations_on_frequency(
    band: str,
    frequency: float,
    latitude: float,
    longitude: float,
    radius_miles: float | None = 200,
) -> pd.DataFrame:
    frame = load_stations()
    tolerance = 0.001 if band != "MW" else 0.1
    matches = frame[(frame["band"] == band) & ((frame["frequency"] - float(frequency)).abs() < tolerance)]
    matches = with_distances(matches, latitude, longitude)
    if radius_miles is not None:
        matches = matches[matches["distance_miles"] <= radius_miles]
    return matches.reset_index(drop=True)


def normalize_call(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())
