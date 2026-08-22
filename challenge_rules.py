"""Compatibility helpers for the file-driven challenge schedule.

Season managers should edit content/challenge_schedule.csv. No Python changes are
required for ordinary schedule additions or revisions.
"""

from __future__ import annotations

from datetime import datetime, timezone

from dxcore.content import active_sprints_for_band, load_challenges


def get_active_challenges() -> list[dict[str, object]]:
    now = datetime.now(timezone.utc)
    return [
        challenge
        for challenge in load_challenges()
        if challenge["start_utc"] <= now <= challenge["end_utc"]
    ]


def get_active_challenge_for_band(
    band: str, challenge_type: str = "sprint"
) -> dict[str, object] | None:
    if challenge_type == "sprint":
        matches = active_sprints_for_band(band)
    else:
        matches = [
            challenge
            for challenge in get_active_challenges()
            if challenge["type"] == challenge_type and band in challenge["bands"]
        ]
    return matches[0] if matches else None
