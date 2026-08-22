from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from dxcore.importers import (
    mapping_for_format,
    normalize_import,
    parse_reception,
    read_upload,
)
from dxcore.store import LocalStore
from dxcore.sheets import HybridStore


STATIONS = pd.DataFrame(
    [
        {
            "station_id": "fm_ktbz",
            "band": "FM",
            "frequency": 94.5,
            "call": "KTBZ",
            "city": "Houston",
            "region": "TX",
            "country": "United States",
            "county": "Harris",
            "grid": "EL29",
            "latitude": 29.76,
            "longitude": -95.37,
        },
        {
            "station_id": "mw_rebelde",
            "band": "MW",
            "frequency": 1180.0,
            "call": "Radio Rebelde (1180)",
            "city": "Marti",
            "region": "DX",
            "country": "Cuba",
            "county": "",
            "grid": "EL92",
            "latitude": 22.95,
            "longitude": -80.92,
        },
    ]
)

LOCATION = {
    "location_id": "qth_test",
    "latitude": 30.36,
    "longitude": -90.07,
    "is_home": 1,
}


class UploadParsingTests(unittest.TestCase):
    def test_fmlist_preamble_and_cp1252_are_parsed_without_guessing_dates(self) -> None:
        content = (
            "Log\nDXer profile\n"
            "Propa;Date;UTC;MHz;ITU;Program;Location;Reg;kW;QRB km;Details;SINPO;RDS;Remarks\n"
            "Tropo;28.06.21;0000;94.50;USA;KTBZ-HD;Houston;TX;1;531;;;;\n"
        ).encode("cp1252")
        parsed = read_upload("fm.csv", content)
        self.assertEqual(parsed.detected_format, "FMList")
        self.assertEqual(len(parsed.frame), 1)
        self.assertEqual(parsed.frame.iloc[0]["Date"], "28.06.21")

    def test_custom_date_protocol_and_local_timezone_are_explicit(self) -> None:
        row = pd.Series({"Date": "03/10/2024", "Time": "01:30"})
        parsed = parse_reception(
            row,
            {"date": "Date", "time": "Time", "timestamp": "<Not mapped>"},
            date_order="MDY",
            time_protocol="Local",
            timezone_name="America/Chicago",
        )
        self.assertEqual(parsed, datetime(2024, 3, 10, 7, 30, tzinfo=timezone.utc))


class NormalizationTests(unittest.TestCase):
    def _normalize(self, frame: pd.DataFrame, source_format: str, existing=None, unlocked=None):
        return normalize_import(
            frame,
            source_format=source_format,
            mapping=mapping_for_format(source_format, frame.columns),
            date_order="MDY",
            time_protocol="UTC",
            timezone_name="UTC",
            fixed_band="",
            default_propagation="Other",
            default_is_sdr=True,
            default_is_portable=False,
            user_id="user",
            location=LOCATION,
            stations=STATIONS,
            existing_logs=existing if existing is not None else pd.DataFrame(),
            unlocked_bands=unlocked if unlocked is not None else {"MW", "FM", "NWR"},
        )

    def test_fmlist_hd_suffix_maps_to_canonical_station(self) -> None:
        frame = pd.DataFrame(
            [{"Propa": "Tropo", "Date": "28.06.21", "UTC": "0000", "MHz": "94.50", "ITU": "USA", "Program": "KTBZ-HD", "Location": "Houston", "Reg": "TX", "Remarks": "RDS"}]
        )
        review = self._normalize(frame, "FMList")
        self.assertEqual(review.iloc[0]["status"], "Ready")
        self.assertEqual(review.iloc[0]["call"], "KTBZ")
        self.assertEqual(review.iloc[0]["propagation"], "Tropo")

    def test_cuban_network_alias_maps_to_one_canonical_name(self) -> None:
        frame = pd.DataFrame(
            [{"Propa": "DX/night", "Date": "01.10.21", "UTC": "0630", "kHz": "1180", "ITU": "CUB", "Program": "R. Rebelde", "Location": "Marti", "Reg": "DX", "Remarks": "ID"}]
        )
        review = self._normalize(frame, "MWList")
        self.assertEqual(review.iloc[0]["status"], "Ready")
        self.assertEqual(review.iloc[0]["call"], "Radio Rebelde (1180)")

    def test_unknown_station_is_held_instead_of_false_positive(self) -> None:
        frame = pd.DataFrame(
            [{"Propa": "Tropo", "Date": "28.06.21", "UTC": "0000", "MHz": "94.50", "ITU": "USA", "Program": "NOT-A-STATION", "Location": "Houston", "Reg": "TX"}]
        )
        review = self._normalize(frame, "FMList")
        self.assertEqual(review.iloc[0]["status"], "Needs review")
        self.assertFalse(bool(review.iloc[0]["selected"]))

    def test_duplicate_window_is_inclusive_during_review(self) -> None:
        frame = pd.DataFrame(
            [{"Propa": "Tropo", "Date": "28.06.21", "UTC": "0005", "MHz": "94.50", "ITU": "USA", "Program": "KTBZ", "Location": "Houston", "Reg": "TX"}]
        )
        existing = pd.DataFrame(
            [{"station_id": "fm_ktbz", "reception_utc": "2021-06-28T00:00:00+00:00"}]
        )
        review = self._normalize(frame, "FMList", existing=existing)
        self.assertEqual(review.iloc[0]["status"], "Duplicate")

    def test_locked_band_cannot_be_selected_for_import(self) -> None:
        frame = pd.DataFrame(
            [{"Propa": "Tropo", "Date": "28.06.21", "UTC": "0000", "MHz": "94.50", "ITU": "USA", "Program": "KTBZ", "Location": "Houston", "Reg": "TX"}]
        )
        review = self._normalize(frame, "FMList", unlocked={"MW"})
        self.assertEqual(review.iloc[0]["status"], "Bandscan locked")
        self.assertFalse(bool(review.iloc[0]["selected"]))


class BatchStoreTests(unittest.TestCase):
    database = Path("tests/.dx_import_test.sqlite3")

    def tearDown(self) -> None:
        self.database.unlink(missing_ok=True)

    def test_batch_append_uses_the_final_duplicate_guard(self) -> None:
        self.database.unlink(missing_ok=True)
        store = LocalStore(self.database)
        common = {
            "user_id": "user",
            "location_id": "qth",
            "station_id": "fm_ktbz",
            "band": "FM",
            "frequency": 94.5,
            "call": "KTBZ",
            "station_city": "Houston",
            "station_region": "TX",
            "station_country": "United States",
            "station_county": "Harris",
            "station_grid": "EL29",
            "station_latitude": 29.76,
            "station_longitude": -95.37,
            "distance_miles": 300,
            "propagation": "Tropo",
            "is_sdr": 1,
            "is_portable": 0,
            "notes": "",
            "source": "import_fmlist",
            "import_batch_id": "batch_test",
        }
        rows = [
            {**common, "reception_utc": "2026-06-01T00:00:00+00:00"},
            {**common, "reception_utc": "2026-06-01T00:04:00+00:00"},
        ]
        result = store.append_logs(rows)
        self.assertEqual(result["accepted"], 1)
        self.assertEqual(result["rejected"], 1)

    def test_display_name_change_updates_the_single_remote_user_record(self) -> None:
        class FakeMirror:
            def __init__(self):
                self.synced = []

            def bootstrap(self, local):
                return None

            def upsert_rows(self, sheet_name, rows):
                self.synced.append((sheet_name, rows))

        self.database.unlink(missing_ok=True)
        local = LocalStore(self.database)
        mirror = FakeMirror()
        store = HybridStore(local, mirror)
        store.upsert_user("google-subject", "dxer@example.com", "Google name")
        store.update_user_preferences("google-subject", display_name="Preferred DX name")
        self.assertEqual(
            local.user_profile("google-subject")["display_name"], "Preferred DX name"
        )
        self.assertEqual(mirror.synced[-1][0], "Users")
        self.assertEqual(mirror.synced[-1][1][0]["user_id"], "google-subject")
        self.assertEqual(mirror.synced[-1][1][0]["display_name"], "Preferred DX name")


if __name__ == "__main__":
    unittest.main()
