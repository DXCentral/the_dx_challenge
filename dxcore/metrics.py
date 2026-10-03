from __future__ import annotations

import re

import pandas as pd


COUNTY_SUFFIXES = re.compile(
    r"\b(county|parish|borough|census area|municipality|city and borough|city)\b",
    flags=re.IGNORECASE,
)

CHALLENGE_SCORE_FIELDS = {
    "Unique stations": "station_id",
    "Unique states/provinces": "region_band_key",
    "Unique countries": "country_band_key",
    "Unique 4-character grids": "grid_band_key",
    "Unique counties/parishes": "county_band_key",
}


def grid4(value: object) -> str:
    text = "" if pd.isna(value) else str(value).strip().upper()
    return text[:4] if len(text) >= 4 else ""


def normalize_county(value: object) -> str:
    text = "" if pd.isna(value) else str(value).strip()
    text = COUNTY_SUFFIXES.sub("", text)
    return re.sub(r"[^A-Z0-9]", "", text.upper())


def add_geography_keys(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["grid4"] = result.get("station_grid", pd.Series(index=result.index, dtype=str)).map(grid4)
    bands = result.get("band", pd.Series(index=result.index, dtype=str)).fillna("").astype(str).str.upper()
    countries = result.get("station_country", pd.Series(index=result.index, dtype=str)).fillna("").astype(str).str.upper()
    regions = result.get("station_region", pd.Series(index=result.index, dtype=str)).fillna("").astype(str).str.upper()
    counties = result.get("station_county", pd.Series(index=result.index, dtype=str)).map(normalize_county)
    result["county_key"] = [f"{region}|{county}" if region and county else "" for region, county in zip(regions, counties, strict=False)]
    result["region_band_key"] = [
        f"{band}|{country}|{region}" if region else ""
        for band, country, region in zip(bands, countries, regions, strict=False)
    ]
    result["country_band_key"] = [
        f"{band}|{country}" if country else ""
        for band, country in zip(bands, countries, strict=False)
    ]
    result["grid_band_key"] = [
        f"{band}|{grid}" if grid else ""
        for band, grid in zip(bands, result["grid4"], strict=False)
    ]
    result["county_band_key"] = [
        f"{band}|{county}" if county else ""
        for band, county in zip(bands, result["county_key"], strict=False)
    ]
    return result


def valid_station_coordinates(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize Sheet-sourced coordinates and remove invalid map points."""
    result = frame.copy()
    for column in ("station_latitude", "station_longitude"):
        if column not in result:
            result[column] = pd.Series(index=result.index, dtype=float)
        result[column] = pd.to_numeric(result[column], errors="coerce")
    return result[
        result["station_latitude"].between(-90, 90)
        & result["station_longitude"].between(-180, 180)
    ].copy()


def canonical_daypart(value: object) -> str:
    text = "" if pd.isna(value) else str(value).strip()
    lowered = text.casefold()
    if "sunrise" in lowered:
        return "Sunrise grayline"
    if "sunset" in lowered:
        return "Sunset grayline"
    if "daytime" in lowered:
        return "Daytime"
    if "nighttime" in lowered:
        return "Nighttime"
    return text


def canonical_propagation(value: object) -> str:
    text = "" if pd.isna(value) else str(value).strip()
    lowered = text.casefold()
    if "groundwave" in lowered or "daytime" in lowered:
        return "Groundwave"
    if "skywave" in lowered or "nighttime" in lowered:
        return "Skywave"
    aliases = {
        "es": "Sporadic E",
        "sporadic e": "Sporadic E",
        "tr": "Tropo",
        "tropo": "Tropo",
        "ms": "Meteor Scatter",
        "meteor scatter": "Meteor Scatter",
        "au": "Aurora",
        "aurora": "Aurora",
        "as": "Aircraft Scatter",
        "aircraft scatter": "Aircraft Scatter",
        "local": "Local",
    }
    return aliases.get(lowered, text)


def challenge_scores(logs: pd.DataFrame, scoring_method: str) -> pd.DataFrame:
    if logs.empty:
        return pd.DataFrame(columns=["user_id", "score"])
    rows = add_geography_keys(logs)
    if scoring_method == "Total receptions":
        return rows.groupby("user_id").size().reset_index(name="score").sort_values("score", ascending=False)
    # Geography keys include the band, so the same state, country, grid, or
    # county can score once on each band in a multi-band sprint.
    field = CHALLENGE_SCORE_FIELDS.get(scoring_method, "station_id")
    valid = rows[rows[field].fillna("").astype(str).str.strip() != ""]
    return (
        valid.groupby("user_id")[field]
        .nunique()
        .reset_index(name="score")
        .sort_values("score", ascending=False)
    )


def challenge_band_scores(logs: pd.DataFrame, scoring_method: str) -> pd.DataFrame:
    """Return each DXer's challenge score broken out across all three bands."""
    columns = ["user_id", "MW", "FM", "NWR"]
    if logs.empty:
        return pd.DataFrame(columns=columns)
    rows = add_geography_keys(logs)
    result = rows[["user_id"]].drop_duplicates().reset_index(drop=True)
    field = CHALLENGE_SCORE_FIELDS.get(scoring_method, "station_id")
    for band in ("MW", "FM", "NWR"):
        band_rows = rows[rows["band"].fillna("").astype(str).str.upper().eq(band)]
        if scoring_method == "Total receptions":
            counts = band_rows.groupby("user_id").size()
        else:
            valid = band_rows[
                band_rows[field].fillna("").astype(str).str.strip() != ""
            ]
            counts = valid.groupby("user_id")[field].nunique()
        result[band] = result["user_id"].map(counts).fillna(0).astype(int)
    return result[columns]
