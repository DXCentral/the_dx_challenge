from __future__ import annotations

import pandas as pd


GRAVEYARD_FREQUENCIES = (1230.0, 1240.0, 1340.0, 1400.0, 1450.0, 1490.0)


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
    rows = rows[rows["frequency_key"].gt(0) & rows["frequency_key"].lt(float("inf"))]
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


def frequency_statistics(history: dict[float, dict[str, object]]) -> pd.DataFrame:
    """Summarize already-scoped history without inflating unique counts on repeats."""
    records = []
    for frequency, summary in history.items():
        rows = summary["rows"].reset_index(drop=True)
        distances = pd.to_numeric(
            rows.get("distance_miles", pd.Series(index=rows.index, dtype=float)),
            errors="coerce",
        )
        distances = distances.where(distances.ge(0) & distances.lt(float("inf")))
        farthest = (
            rows.loc[distances.idxmax()]
            if distances.notna().any()
            else pd.Series(dtype=object)
        )
        place = farthest.reindex(
            ["station_city", "station_region", "station_country"]
        ).fillna("").astype(str).str.strip()
        call = farthest.get("call", "")
        records.append({
            "frequency": float(frequency),
            "unique_stations": int(summary["unique_stations"]),
            "receptions": len(rows),
            "max_distance_miles": distances.max(),
            "farthest_call": "" if pd.isna(call) else str(call),
            "farthest_location": ", ".join(value for value in place if value),
        })
    return pd.DataFrame(records, columns=[
        "frequency", "unique_stations", "receptions", "max_distance_miles",
        "farthest_call", "farthest_location",
    ])
