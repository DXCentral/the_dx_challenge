from __future__ import annotations

import pandas as pd


def interference_level(rows: pd.DataFrame) -> str:
    """Return the local-interference class for one logged frequency."""
    if rows.empty:
        return "unlogged"
    distances = pd.to_numeric(rows.get("distance_miles"), errors="coerce").dropna()
    if not distances.empty and (distances <= 50).any():
        return "local"
    if not distances.empty and (distances <= 200).any():
        return "regional"
    return "open"


def reception_history(
    logs: pd.DataFrame,
    *,
    band: str,
    location_id: str,
) -> dict[float, dict[str, object]]:
    """Summarize one user's submitted receptions by frequency at one QTH."""
    if logs.empty:
        return {}
    rows = logs[
        (logs["band"].astype(str).str.upper() == band.upper())
        & (logs["location_id"].astype(str) == str(location_id))
    ].copy()
    if rows.empty:
        return {}
    rows["frequency_key"] = pd.to_numeric(rows["frequency"], errors="coerce").round(3)
    rows = rows.dropna(subset=["frequency_key"])
    result: dict[float, dict[str, object]] = {}
    for frequency, group in rows.groupby("frequency_key", sort=True):
        station_keys = group["station_id"].fillna("").astype(str)
        fallback = (
            group["call"].fillna("").astype(str)
            + "|"
            + group["station_city"].fillna("").astype(str)
            + "|"
            + group["station_region"].fillna("").astype(str)
        )
        unique_keys = station_keys.where(station_keys.str.strip() != "", fallback)
        result[float(frequency)] = {
            "unique_stations": int(unique_keys.nunique()),
            "interference": interference_level(group),
            "rows": group.sort_values("reception_utc", ascending=False),
        }
    return result
