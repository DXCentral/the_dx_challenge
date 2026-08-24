from __future__ import annotations

from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = APP_ROOT / "assets"
CONTENT_DIR = APP_ROOT / "content"
LOCAL_DATA_DIR = APP_ROOT / ".local"
LOCAL_DB_PATH = LOCAL_DATA_DIR / "dx_challenge_staging_v1.sqlite3"
APP_LOGO_FILE = ASSET_DIR / "dx_challenge_logo.png"
APP_VERSION = "1.0.0-rc5.1"

STAGING_SPREADSHEET_ID = "1Z0C_bnxCgVMWdhP26MbvKqsGCNcCab0zeSQiIpJzn2A"
DEFAULT_USER_ID = "local-tester@dxcentralonline.com"
DEFAULT_USER_NAME = "Local tester"

STATION_FILES = {
    "mw": APP_ROOT / "Mesa_Mike_Season_7_Enriched.csv",
    "mw_international": APP_ROOT
    / "MW International Station List - Season 7 - 081626 - Season 7 International Station List.csv",
    "fm": APP_ROOT / "WTFDA_Season_7_Enriched.csv",
    "nwr": APP_ROOT / "NWR_Transmitters_Cleaned.csv",
    "nwr_counties": APP_ROOT / "NWR_Station_Counties.csv",
}

COUNTY_REFERENCE_FILE = ASSET_DIR / "us_county_reference.csv"
COUNTY_GEOJSON_FILE = ASSET_DIR / "us_counties_5m.geojson"
