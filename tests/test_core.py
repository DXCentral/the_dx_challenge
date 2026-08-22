from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from dxcore.content import frequency_allowed, load_challenges
from dxcore.geo import grid_to_latlon, haversine_miles, latlon_to_grid
from dxcore.metrics import add_geography_keys, canonical_daypart
from dxcore.solar import mw_propagation
from dxcore.stations import load_stations, stations_on_frequency
from dxcore.store import LocalStore


class StationTests(unittest.TestCase):
    def test_station_snapshot_normalizes_all_bands(self) -> None:
        frame = load_stations()
        self.assertGreater(len(frame), 20_000)
        self.assertEqual(set(frame["band"]), {"MW", "FM", "NWR"})
        self.assertFalse(frame["station_id"].duplicated().any())

    def test_frequency_lookup_is_distance_sorted(self) -> None:
        frame = stations_on_frequency("FM", 90.7, 30.36, -90.06, radius_miles=None)
        self.assertFalse(frame.empty)
        self.assertTrue(frame["distance_miles"].is_monotonic_increasing)

    def test_bogalusa_nwr_uses_transmitter_parish(self) -> None:
        frame = load_stations()
        station = frame[
            (frame["band"] == "NWR")
            & (frame["call"] == "WNG521")
            & ((frame["frequency"] - 162.525).abs() < 0.001)
        ].iloc[0]
        self.assertEqual(station["county"], "Washington")
        self.assertEqual(station["region"], "LA")


class GeographyTests(unittest.TestCase):
    def test_maidenhead_round_trip(self) -> None:
        latitude, longitude = grid_to_latlon("EM40")
        self.assertEqual(latlon_to_grid(latitude, longitude, precision=4), "EM40")

    def test_haversine_identity(self) -> None:
        self.assertAlmostEqual(haversine_miles(30.0, -90.0, 30.0, -90.0), 0.0)

    def test_mw_diurnal_mode(self) -> None:
        daytime = datetime(2026, 6, 21, 18, 0, tzinfo=timezone.utc)
        nighttime = datetime(2026, 6, 21, 6, 0, tzinfo=timezone.utc)
        self.assertEqual(mw_propagation(daytime, 30.36, -90.06), "Groundwave / Daytime")
        self.assertEqual(mw_propagation(nighttime, 30.36, -90.06), "Skywave / Nighttime")

    def test_grid_and_county_awards_use_canonical_keys(self) -> None:
        frame = add_geography_keys(
            pd.DataFrame(
                {
                    "station_grid": ["EM40AB", "EM40CD", "EN50AA"],
                    "station_region": ["LA", "LA", "IL"],
                    "station_county": ["Washington Parish", "Washington", "Washington County"],
                }
            )
        )
        self.assertEqual(frame["grid4"].nunique(), 2)
        self.assertEqual(frame["county_key"].nunique(), 2)
        self.assertEqual(canonical_daypart("Groundwave / Daytime"), "Daytime")

    def test_file_driven_challenge_schedule(self) -> None:
        challenge = next(item for item in load_challenges() if item["id"] == "week_1_910_sprint")
        self.assertTrue(frequency_allowed(challenge["rules"]["frequencies"], 910.0))
        self.assertFalse(frequency_allowed(challenge["rules"]["frequencies"], 920.0))


class StoreTests(unittest.TestCase):
    database = Path("tests/.dx_test.sqlite3")

    def setUp(self) -> None:
        self.database.unlink(missing_ok=True)
        self.store = LocalStore(self.database)
        self.user_id = "tester@example.com"
        self.store.upsert_user(self.user_id, self.user_id, "Tester")
        self.location_id = self.store.add_location(
            self.user_id,
            {
                "label": "Home",
                "city": "Mandeville",
                "region": "LA",
                "country": "United States",
                "grid": "EM40",
                "latitude": 30.36,
                "longitude": -90.06,
                "is_home": True,
            },
        )

    def tearDown(self) -> None:
        self.database.unlink(missing_ok=True)

    def _log(self, reception: datetime) -> dict[str, object]:
        return {
            "user_id": self.user_id,
            "location_id": self.location_id,
            "station_id": "fm_example",
            "band": "FM",
            "frequency": 90.7,
            "call": "TEST",
            "station_city": "New Orleans",
            "station_region": "LA",
            "station_country": "United States",
            "station_county": "Orleans",
            "station_grid": "EL49",
            "station_latitude": 29.95,
            "station_longitude": -90.07,
            "reception_utc": reception.isoformat(),
            "distance_miles": 28.4,
            "propagation": "Local",
            "is_sdr": 0,
            "is_portable": 0,
            "notes": "",
            "source": "station_list",
        }

    def test_duplicate_window_is_inclusive(self) -> None:
        original = datetime(2026, 9, 5, 2, 0, tzinfo=timezone.utc)
        accepted, _ = self.store.append_log(self._log(original))
        self.assertTrue(accepted)
        accepted, _ = self.store.append_log(self._log(original + timedelta(minutes=5)))
        self.assertFalse(accepted)
        accepted, _ = self.store.append_log(self._log(original + timedelta(minutes=6)))
        self.assertTrue(accepted)
        self.assertEqual(len(self.store.logs(self.user_id)), 2)

    def test_bandscan_is_scoped_to_location(self) -> None:
        self.store.save_bandscan(self.user_id, self.location_id, "FM", 88.1, "OPEN", call="OPEN")
        scan = self.store.bandscan(self.user_id, self.location_id, "FM")
        self.assertEqual(len(scan), 1)
        self.assertEqual(scan.iloc[0]["status"], "OPEN")

    def test_log_can_be_updated_and_soft_deleted_by_stable_id(self) -> None:
        reception = datetime(2026, 9, 5, 2, 0, tzinfo=timezone.utc)
        accepted, log_id = self.store.append_log(self._log(reception))
        self.assertTrue(accepted)
        updated, _ = self.store.update_log(
            self.user_id,
            log_id,
            {"notes": "Corrected details", "propagation": "Tropo"},
        )
        self.assertTrue(updated)
        record = self.store.logs(self.user_id).iloc[0]
        self.assertEqual(record["notes"], "Corrected details")
        self.assertEqual(record["revision"], 2)
        deleted, _ = self.store.delete_log(self.user_id, log_id)
        self.assertTrue(deleted)
        self.assertTrue(self.store.logs(self.user_id).empty)

    def test_location_with_logs_is_locked_from_deletion(self) -> None:
        accepted, _ = self.store.append_log(self._log(datetime(2026, 9, 5, 2, 0, tzinfo=timezone.utc)))
        self.assertTrue(accepted)
        deleted, message = self.store.delete_location(self.user_id, self.location_id)
        self.assertFalse(deleted)
        self.assertIn("locked", message)

    def test_custom_display_name_survives_google_identity_refresh(self) -> None:
        self.store.update_user_preferences(
            self.user_id,
            display_name="Robert",
            theme_name="High contrast",
            walkthrough_complete=True,
        )
        self.store.upsert_user(self.user_id, self.user_id, "Google Account Name")
        profile = self.store.user_profile(self.user_id)
        self.assertEqual(profile["display_name"], "Robert")
        self.assertEqual(profile["theme_name"], "High contrast")
        self.assertEqual(profile["walkthrough_complete"], 1)


if __name__ == "__main__":
    unittest.main()
