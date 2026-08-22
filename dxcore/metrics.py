from __future__ import annotations

import re

import pandas as pd


COUNTY_SUFFIXES = re.compile(
    r"\b(county|parish|borough|census area|municipality|city and borough|city)\b",
    flags=re.IGNORECASE,
)


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
    regions = result.get("station_region", pd.Series(index=result.index, dtype=str)).fillna("").astype(str).str.upper()
    counties = result.get("station_county", pd.Series(index=result.index, dtype=str)).map(normalize_county)
    result["county_key"] = [f"{region}|{county}" if region and county else "" for region, county in zip(regions, counties, strict=False)]
    return result


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
