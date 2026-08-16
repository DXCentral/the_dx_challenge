import datetime
from datetime import timezone

# =========================================================================
# 🎯 THE DX CHALLENGE: SEASON 7 - FORM LOCKER & STATE MACHINE
# All times are handled strictly in UTC to prevent local timezone drift.
# =========================================================================

SEASON_7_START = datetime.datetime(2026, 9, 5, 2, 0, tzinfo=timezone.utc)
SEASON_7_END = datetime.datetime(2027, 8, 31, 23, 59, 59, tzinfo=timezone.utc)

CHALLENGES = [
    # ==========================================
    # 🏃 SEASON-LONG MARATHONS (Always Active)
    # ==========================================
    {
        "id": "season_7_mw_marathon",
        "type": "marathon",
        "timeframe_tag": "Season 7 | MW",
        "name": "Season 7 MW Marathon",
        "band": "MW",
        "start_utc": SEASON_7_START,
        "end_utc": SEASON_7_END,
        "rules": {
            "frequencies": "ALL",
            "regions": ["ALL"],
            "pts_per_100_miles": 1.0
        }
    },
    {
        "id": "season_7_fm_marathon",
        "type": "marathon",
        "timeframe_tag": "Season 7 | FM",
        "name": "Season 7 FM Marathon",
        "band": "FM",
        "start_utc": SEASON_7_START,
        "end_utc": SEASON_7_END,
        "rules": {
            "frequencies": "ALL",
            "regions": ["ALL"],
            "pts_per_100_miles": 1.0
        }
    },
    {
        "id": "season_7_nwr_marathon",
        "type": "marathon",
        "timeframe_tag": "Season 7 | NWR",
        "name": "Season 7 NWR Marathon",
        "band": "NWR",
        "start_utc": SEASON_7_START,
        "end_utc": SEASON_7_END,
        "rules": {
            "frequencies": "ALL",
            "regions": ["ALL"],
            "pts_per_100_miles": 1.0
        }
    },

    # ==========================================
    # ⚠️ WEEKLY SPRINTS (Rotating)
    # ==========================================
    {
        "id": "week_1_launch_sprint",
        "type": "sprint",
        "timeframe_tag": "Week 1 | 910 kHz",
        "name": "The 910 kHz Sprint",
        "band": "MW",
        "start_utc": datetime.datetime(2026, 9, 5, 2, 0, tzinfo=timezone.utc),
        "end_utc": datetime.datetime(2026, 9, 12, 2, 0, tzinfo=timezone.utc),
        "rules": {
            "frequencies": [910],
            "regions": ["ALL"],
            "pts_per_100_miles": 1.0
        }
    }
]

def get_active_challenges():
    """
    Scans the CHALLENGES array and returns a list of dictionaries 
    for every challenge currently active based on the live UTC clock.
    """
    now = datetime.datetime.now(timezone.utc)
    return [c for c in CHALLENGES if c["start_utc"] <= now <= c["end_utc"]]

def get_active_challenge_for_band(band, challenge_type="sprint"):
    """
    Returns the specific active challenge dictionary for a selected band and type.
    Used by the Streamlit forms to dynamically lock frequency/region inputs.
    """
    now = datetime.datetime.now(timezone.utc)
    for c in CHALLENGES:
        if c["start_utc"] <= now <= c["end_utc"] and c["band"] == band and c["type"] == challenge_type:
            return c
    return None
