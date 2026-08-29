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
    fields = {
        "Unique stations": "station_id",
        "Unique states/provinces": "station_region",
        "Unique countries": "station_country",
        "Unique 4-character grids": "grid4",
        "Unique counties/parishes": "county_key",
    }
    if scoring_method == "Total receptions":
        return rows.groupby("user_id").size().reset_index(name="score").sort_values("score", ascending=False)
    field = fields.get(scoring_method, "station_id")
    valid = rows[rows[field].fillna("").astype(str).str.strip() != ""]
    return (
        valid.groupby("user_id")[field]
        .nunique()
        .reset_index(name="score")
        .sort_values("score", ascending=False)
    )
