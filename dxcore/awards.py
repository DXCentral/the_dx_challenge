from __future__ import annotations

import pandas as pd

from dxcore.metrics import add_geography_keys, canonical_daypart, canonical_propagation


AWARDS: dict[str, dict[str, object]] = {
    "MW · MW Master": {"band": "MW", "field": "station_id", "target": 700, "endorsement": 100, "unit": "unique stations"},
    "MW · Grid Hunter": {"band": "MW", "field": "grid4", "target": 200, "endorsement": 50, "unit": "unique 4-character grids"},
    "MW · County Hunter": {"band": "MW", "field": "county_key", "target": 200, "endorsement": 50, "unit": "unique counties/parishes"},
    "MW · International DXer": {"band": "MW", "field": "station_country", "target": 20, "endorsement": 5, "unit": "unique countries"},
    "MW · Domestic DXer": {"band": "MW", "field": "station_region", "target": 48, "endorsement": None, "unit": "Lower 48 states"},
    "MW · MW Propagation Master": {"band": "MW", "components": {"Daytime": 20, "Sunrise grayline": 150, "Sunset grayline": 150, "Nighttime": 200}},
    "MW · The Gravedigger": {"band": "MW", "field": "station_id", "target": 150, "endorsement": None, "unit": "unique graveyard stations", "graveyard": True},
    "MW · Master Gravedigger": {"band": "MW", "field": "station_id", "target": 200, "endorsement": None, "unit": "unique graveyard stations", "graveyard": True, "long_distance": 10},
    "FM · FM Master": {"band": "FM", "field": "station_id", "target": 1000, "endorsement": 200, "unit": "unique stations"},
    "FM · Grid Hunter": {"band": "FM", "field": "grid4", "target": 200, "endorsement": 50, "unit": "unique 4-character grids"},
    "FM · County Hunter": {"band": "FM", "field": "county_key", "target": 200, "endorsement": 50, "unit": "unique counties/parishes"},
    "FM · Propagation Master": {"band": "FM", "components": {"Tropo": 100, "Meteor Scatter": 100, "Sporadic E": 100}},
    "NWR · NWR Master": {"band": "NWR", "field": "station_id", "target": 100, "endorsement": None, "unit": "unique stations"},
    "NWR · Grid Hunter": {"band": "NWR", "field": "grid4", "target": 50, "endorsement": 10, "unit": "unique 4-character grids"},
    "NWR · County Hunter": {"band": "NWR", "field": "county_key", "target": 50, "endorsement": 10, "unit": "unique counties/parishes"},
    "NWR · WFO Hunter": {"band": "NWR", "field": "wfo", "target": 50, "endorsement": 10, "unit": "unique Weather Forecast Offices"},
    "NWR · Propagation Master": {"band": "NWR", "components": {"Tropo": 5, "Meteor Scatter": 5, "Sporadic E": 5}},
}

GRAVEYARD = {1230.0, 1240.0, 1340.0, 1400.0, 1450.0, 1490.0}
LOWER_48 = {"AL", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY"}


def qualifying_rows(logs: pd.DataFrame, rule: dict[str, object]) -> pd.DataFrame:
    if logs.empty or "band" not in logs:
        return pd.DataFrame()
    rows = add_geography_keys(logs[logs["band"] == rule["band"]])
    if rule.get("graveyard"):
        rows = rows[pd.to_numeric(rows["frequency"], errors="coerce").isin(GRAVEYARD)]
    if rule.get("field") == "station_region":
        rows = rows[rows["station_region"].astype(str).str.upper().isin(LOWER_48)]
    return rows


def simple_progress(rows: pd.DataFrame, rule: dict[str, object]) -> pd.DataFrame:
    field = str(rule["field"])
    if rows.empty or field not in rows:
        return pd.DataFrame(columns=["user_id", "count"])
    valid = rows[rows[field].fillna("").astype(str).str.strip() != ""]
    return (
        valid.groupby("user_id")[field]
        .nunique()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
    )


def _award_propagation(rows: pd.DataFrame, band: str) -> pd.Series:
    mapper = canonical_daypart if band == "MW" else canonical_propagation
    return rows["propagation"].map(mapper)


def component_progress(
    rows: pd.DataFrame, components: dict[str, int], band: str | None = None
) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame(columns=["user_id", *components, "count", "progress"])
    eligible = (
        rows[rows["source"] != "bandscan"]
        .sort_values("reception_utc")
        .drop_duplicates(["user_id", "station_id"])
        .copy()
    )
    eligible["award_propagation"] = _award_propagation(
        eligible, band or str(rows["band"].iloc[0])
    )
    pivot = (
        eligible.groupby(["user_id", "award_propagation"])["station_id"]
        .nunique()
        .unstack(fill_value=0)
    )
    for component in components:
        if component not in pivot:
            pivot[component] = 0
    pivot = pivot[list(components)].reset_index()
    pivot["count"] = pivot[list(components)].sum(axis=1)
    pivot["progress"] = pivot.apply(
        lambda row: min(row[name] / target for name, target in components.items()), axis=1
    )
    return pivot.sort_values(["progress", "count"], ascending=False)


def award_milestones(
    logs: pd.DataFrame, display_name_lookup: dict[str, str] | None = None
) -> pd.DataFrame:
    """Return earned award and endorsement events with their first-achieved UTC time."""
    columns = ["achieved_utc", "user_id", "dxer", "award", "milestone", "summary"]
    if logs.empty:
        return pd.DataFrame(columns=columns)
    lookup = display_name_lookup or {}
    events: list[dict[str, object]] = []
    for award_key, rule in AWARDS.items():
        rows = qualifying_rows(logs, rule)
        if rows.empty or (rule.get("field") == "wfo" and "wfo" not in rows):
            continue
        rows = rows.copy()
        rows["_received"] = pd.to_datetime(rows["reception_utc"], errors="coerce", utc=True)
        rows = rows.dropna(subset=["_received"])
        if "components" in rule:
            components = {str(name): int(target) for name, target in rule["components"].items()}
            eligible = (
                rows[rows["source"] != "bandscan"]
                .sort_values("_received")
                .drop_duplicates(["user_id", "station_id"])
                .copy()
            )
            eligible["award_propagation"] = _award_propagation(
                eligible, str(rule["band"])
            )
            for user_id, user_rows in eligible.groupby("user_id"):
                crossing_dates: list[pd.Timestamp] = []
                component_summary: list[str] = []
                for component, target in components.items():
                    component_rows = user_rows[
                        user_rows["award_propagation"] == component
                    ].sort_values("_received")
                    count = int(component_rows["station_id"].nunique())
                    component_summary.append(f"{component} {count:,}/{target:,}")
                    if count < target:
                        break
                    unique_rows = component_rows.drop_duplicates("station_id")
                    crossing_dates.append(unique_rows.iloc[target - 1]["_received"])
                else:
                    achieved = max(crossing_dates)
                    events.append(
                        {
                            "achieved_utc": achieved,
                            "user_id": str(user_id),
                            "dxer": lookup.get(str(user_id), "DXer"),
                            "award": award_key,
                            "milestone": f"{award_key} qualified",
                            "summary": " · ".join(component_summary),
                        }
                    )
            continue

        field = str(rule["field"])
        if field not in rows:
            continue
        target = int(rule["target"])
        endorsement = int(rule["endorsement"]) if rule.get("endorsement") else None
        for user_id, user_rows in rows.groupby("user_id"):
            unique_rows = (
                user_rows[user_rows[field].fillna("").astype(str).str.strip() != ""]
                .sort_values("_received")
                .drop_duplicates(field)
            )
            count = len(unique_rows)
            if count < target:
                continue
            achieved = unique_rows.iloc[target - 1]["_received"]
            if rule.get("long_distance"):
                long_rows = unique_rows[
                    pd.to_numeric(unique_rows["distance_miles"], errors="coerce") >= 800
                ]
                required_long = int(rule["long_distance"])
                if len(long_rows) < required_long:
                    continue
                achieved = max(achieved, long_rows.iloc[required_long - 1]["_received"])
            events.append(
                {
                    "achieved_utc": achieved,
                    "user_id": str(user_id),
                    "dxer": lookup.get(str(user_id), "DXer"),
                    "award": award_key,
                    "milestone": award_key,
                    "summary": f"{target:,} {rule['unit']}",
                }
            )
            if endorsement:
                threshold = target + endorsement
                while threshold <= count:
                    events.append(
                        {
                            "achieved_utc": unique_rows.iloc[threshold - 1]["_received"],
                            "user_id": str(user_id),
                            "dxer": lookup.get(str(user_id), "DXer"),
                            "award": award_key,
                            "milestone": f"{award_key} · {threshold:,} endorsement",
                            "summary": f"{threshold:,} {rule['unit']}",
                        }
                    )
                    threshold += endorsement
    if not events:
        return pd.DataFrame(columns=columns)
    return (
        pd.DataFrame(events, columns=columns)
        .sort_values(["achieved_utc", "dxer", "award"], ascending=[False, True, True])
        .reset_index(drop=True)
    )
