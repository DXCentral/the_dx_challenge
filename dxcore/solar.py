from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta, timezone


def _normalize_degrees(value: float) -> float:
    return value % 360


def _event_utc(day: date, latitude: float, longitude: float, sunrise: bool) -> datetime | None:
    """Approximate official sunrise/sunset using the NOAA sunrise equation."""
    day_of_year = day.timetuple().tm_yday
    longitude_hour = longitude / 15
    estimate = day_of_year + ((6 - longitude_hour) / 24 if sunrise else (18 - longitude_hour) / 24)
    mean_anomaly = (0.9856 * estimate) - 3.289
    true_longitude = _normalize_degrees(
        mean_anomaly
        + 1.916 * math.sin(math.radians(mean_anomaly))
        + 0.020 * math.sin(math.radians(2 * mean_anomaly))
        + 282.634
    )
    right_ascension = _normalize_degrees(
        math.degrees(math.atan(0.91764 * math.tan(math.radians(true_longitude))))
    )
    longitude_quadrant = math.floor(true_longitude / 90) * 90
    ascension_quadrant = math.floor(right_ascension / 90) * 90
    right_ascension = (right_ascension + longitude_quadrant - ascension_quadrant) / 15
    sin_declination = 0.39782 * math.sin(math.radians(true_longitude))
    cos_declination = math.cos(math.asin(sin_declination))
    cos_hour = (
        math.cos(math.radians(90.833))
        - sin_declination * math.sin(math.radians(latitude))
    ) / (cos_declination * math.cos(math.radians(latitude)))
    if cos_hour < -1 or cos_hour > 1:
        return None
    hour_angle = 360 - math.degrees(math.acos(cos_hour)) if sunrise else math.degrees(math.acos(cos_hour))
    local_hour = hour_angle / 15
    local_mean_time = local_hour + right_ascension - (0.06571 * estimate) - 6.622
    utc_hours = (local_mean_time - longitude_hour) % 24
    midnight = datetime.combine(day, time.min, tzinfo=timezone.utc)
    return midnight + timedelta(hours=utc_hours)


def mw_propagation(reception_utc: datetime, latitude: float, longitude: float) -> str:
    """Classify MW propagation from the receiving QTH's solar events.

    Sunrise and sunset each cover the event minute plus or minus 60 minutes.
    Daytime begins at minute 61 after sunrise and ends at minute 61 before
    sunset; the remaining period is nighttime.
    """
    reception_minute = reception_utc.astimezone(timezone.utc).replace(second=0, microsecond=0)
    events: list[tuple[datetime, str]] = []
    for offset in (-1, 0, 1):
        event_day = reception_minute.date() + timedelta(days=offset)
        for is_sunrise, label in ((True, "sunrise"), (False, "sunset")):
            event = _event_utc(event_day, latitude, longitude, sunrise=is_sunrise)
            if event is not None:
                events.append((event.replace(second=0, microsecond=0), label))
    if not events:
        return "MW automatic — polar day/night review"
    grayline = timedelta(minutes=60)
    nearby = sorted(
        (
            (abs((reception_minute - instant).total_seconds()), label)
            for instant, label in events
            if instant - grayline <= reception_minute <= instant + grayline
        ),
        key=lambda item: item[0],
    )
    if nearby:
        return "Sunrise grayline" if nearby[0][1] == "sunrise" else "Sunset grayline"

    earlier = [(instant, label) for instant, label in events if instant < reception_minute]
    if not earlier:
        return "MW automatic — polar day/night review"
    return (
        "Groundwave / Daytime"
        if max(earlier, key=lambda item: item[0])[1] == "sunrise"
        else "Skywave / Nighttime"
    )
