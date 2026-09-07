from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from dxcore.bandscan import reception_history
from dxcore.content import (
    allowed_challenge_frequencies,
    challenge_log_mask,
    challenges_from_frame,
    frequency_allowed,
    load_challenges,
    log_qualifies,
    logs_qualifying_for_challenges,
    station_qualifies_for_challenge,
    validate_season_submission,
)
from dxcore.geo import (
    grid_to_latlon,
    haversine_miles,
    latlon_to_grid,
    repair_geography,
    resolve_place,
    valid_coordinates,
)
from dxcore.metrics import (
    add_geography_keys,
    canonical_daypart,
    canonical_propagation,
    challenge_scores,
    valid_station_coordinates,
)
from dxcore.solar import _event_utc, mw_propagation
from dxcore.stations import load_stations, stations_on_frequency
from dxcore.store import LocalStore
from dxcore.presentation import convert_distance, format_reception


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
    class FakeGeocoder:
        def __init__(self) -> None:
            self.query = ""

        def geocode(self, query: str, **kwargs: object):
            self.query = query
            self.kwargs = kwargs
            return type(
                "Result",
                (),
                {
                    "latitude": 30.3583,
                    "longitude": -90.0656,
                    "address": "Mandeville, St. Tammany Parish, Louisiana, United States",
                },
            )()

    def test_maidenhead_round_trip(self) -> None:
        latitude, longitude = grid_to_latlon("EM40")
        self.assertEqual(latlon_to_grid(latitude, longitude, precision=4), "EM40")

    def test_haversine_identity(self) -> None:
        self.assertAlmostEqual(haversine_miles(30.0, -90.0, 30.0, -90.0), 0.0)

    def test_map_coordinates_normalize_mixed_sheet_types(self) -> None:
        frame = pd.DataFrame(
            {
                "station_latitude": [29.9, "30.1", "not-a-number", "95"],
                "station_longitude": ["-90.1", -91.2, "80", "-90"],
                "band": ["MW", "FM", "NWR", "MW"],
            }
        )
        valid = valid_station_coordinates(frame)
        self.assertEqual(valid["band"].tolist(), ["MW", "FM"])
        self.assertTrue(pd.api.types.is_float_dtype(valid["station_latitude"]))
        self.assertAlmostEqual(valid["station_longitude"].mean(), -90.65)

    def test_city_region_lookup_always_derives_coordinates_and_grid(self) -> None:
        geocoder = self.FakeGeocoder()
        result = resolve_place("Mandeville", "LA", "United States", geocoder)
        self.assertEqual(geocoder.query, "Mandeville, LA, United States")
        self.assertTrue(geocoder.kwargs["addressdetails"])
        self.assertTrue(valid_coordinates(result["latitude"], result["longitude"]))
        self.assertEqual(result["grid"], latlon_to_grid(30.3583, -90.0656))

    def test_saved_grid_can_repair_missing_coordinates_without_network(self) -> None:
        repaired = repair_geography({"grid": "EM40XI", "latitude": "", "longitude": ""})
        self.assertTrue(valid_coordinates(repaired["latitude"], repaired["longitude"]))
        self.assertEqual(repaired["grid"], "EM40XI")

    def test_mw_diurnal_mode(self) -> None:
        daytime = datetime(2026, 6, 21, 18, 0, tzinfo=timezone.utc)
        nighttime = datetime(2026, 6, 21, 6, 0, tzinfo=timezone.utc)
        self.assertEqual(mw_propagation(daytime, 30.36, -90.06), "Groundwave / Daytime")
        self.assertEqual(mw_propagation(nighttime, 30.36, -90.06), "Skywave / Nighttime")

    def test_mw_grayline_boundaries_follow_the_published_minute_windows(self) -> None:
        day = datetime(2026, 6, 21, tzinfo=timezone.utc).date()
        sunrise = _event_utc(day, 30.36, -90.06, sunrise=True).replace(second=0, microsecond=0)
        sunset = _event_utc(day, 30.36, -90.06, sunrise=False).replace(second=0, microsecond=0)
        self.assertEqual(mw_propagation(sunrise - timedelta(minutes=60), 30.36, -90.06), "Sunrise grayline")
        self.assertEqual(mw_propagation(sunrise + timedelta(minutes=60), 30.36, -90.06), "Sunrise grayline")
        self.assertEqual(mw_propagation(sunrise + timedelta(minutes=61), 30.36, -90.06), "Groundwave / Daytime")
        self.assertEqual(mw_propagation(sunset - timedelta(minutes=60), 30.36, -90.06), "Sunset grayline")
        self.assertEqual(mw_propagation(sunset + timedelta(minutes=60), 30.36, -90.06), "Sunset grayline")
        self.assertEqual(mw_propagation(sunset + timedelta(minutes=61), 30.36, -90.06), "Skywave / Nighttime")

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
        self.assertEqual(
            allowed_challenge_frequencies(challenge, [900.0, 909.0, 910.0, 920.0]),
            [910.0],
        )

    def test_challenge_station_filter_and_final_log_use_same_geography_rules(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "challenge_id": "us_only",
                    "challenge_type": "sprint",
                    "challenge_name": "US only",
                    "start_utc": "2026-09-01T00:00:00Z",
                    "end_utc": "2026-09-30T23:59:59Z",
                    "bands": "FM",
                    "frequencies": "ALL",
                    "include_countries": "United States",
                    "min_distance": "100",
                    "scoring_method": "Unique states/provinces",
                    "active": "true",
                }
            ]
        ).fillna("")
        challenge = challenges_from_frame(frame)[0]
        station = {
            "band": "FM",
            "frequency": 94.5,
            "country": "United States",
            "region": "TX",
            "distance_miles": 300,
        }
        self.assertTrue(station_qualifies_for_challenge(station, challenge))
        log = {
            "band": "FM",
            "frequency": 94.5,
            "station_country": "United States",
            "station_region": "TX",
            "distance_miles": 300,
            "reception_utc": "2026-09-10T02:00:00Z",
            "propagation": "Tropo",
        }
        self.assertTrue(log_qualifies(log, challenge))
        log["source"] = "bulk_import"
        self.assertTrue(log_qualifies(log, challenge))
        log["station_country"] = "Mexico"
        self.assertFalse(log_qualifies(log, challenge))

    def test_marathon_eligibility_excludes_out_of_window_logs_without_deleting_them(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "challenge_id": "season_fm",
                    "challenge_type": "marathon",
                    "challenge_name": "Season FM",
                    "start_utc": "2026-09-01T00:00:00Z",
                    "end_utc": "2026-09-10T23:59:59Z",
                    "bands": "FM",
                    "frequencies": "ALL",
                    "active": "true",
                }
            ]
        ).fillna("")
        challenge = challenges_from_frame(frame)[0]
        logs = pd.DataFrame(
            [
                {
                    "log_id": "old",
                    "band": "FM",
                    "frequency": 94.5,
                    "station_country": "United States",
                    "station_region": "TX",
                    "distance_miles": 300,
                    "reception_utc": "2026-08-31T23:59:59Z",
                    "propagation": "Tropo",
                },
                {
                    "log_id": "eligible",
                    "band": "FM",
                    "frequency": 94.5,
                    "station_country": "United States",
                    "station_region": "TX",
                    "distance_miles": 300,
                    "reception_utc": "2026-09-05T12:00:00Z",
                    "propagation": "Tropo",
                },
                {
                    "log_id": "wrong-band",
                    "band": "MW",
                    "frequency": 910,
                    "station_country": "United States",
                    "station_region": "TX",
                    "distance_miles": 300,
                    "reception_utc": "2026-09-05T12:00:00Z",
                    "propagation": "Skywave / Nighttime",
                },
            ]
        )
        eligible = logs_qualifying_for_challenges(logs, [challenge])
        self.assertEqual(eligible["log_id"].tolist(), ["eligible"])
        self.assertEqual(len(logs), 3)

    def test_vectorized_challenge_rules_match_single_log_validation(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "challenge_id": "specific_fm",
                    "challenge_type": "sprint",
                    "challenge_name": "Specific FM",
                    "start_utc": "2026-09-01T00:00:00Z",
                    "end_utc": "2026-09-10T23:59:59Z",
                    "bands": "FM",
                    "frequencies": "94.5|100.1-100.5",
                    "include_countries": "United States",
                    "exclude_regions": "TX",
                    "propagation_modes": "Tropo",
                    "min_distance": "100",
                    "max_distance": "500",
                    "active": "true",
                }
            ]
        ).fillna("")
        challenge = challenges_from_frame(frame)[0]
        valid = {
            "band": "FM", "frequency": 94.5, "station_country": "United States",
            "station_region": "LA", "distance_miles": 300,
            "reception_utc": "2026-09-05T12:00:00Z", "propagation": "Tropo",
        }
        records = [
            valid,
            {**valid, "frequency": 95.1},
            {**valid, "station_country": "Canada"},
            {**valid, "station_region": "TX"},
            {**valid, "distance_miles": 50},
            {**valid, "propagation": "Sporadic E"},
            {**valid, "reception_utc": "2026-09-11T00:00:00Z"},
        ]
        rows = pd.DataFrame(records)
        expected = rows.apply(lambda row: log_qualifies(row, challenge), axis=1)
        self.assertEqual(challenge_log_mask(rows, challenge).tolist(), expected.tolist())

    def test_submission_requires_marathon_and_adds_matching_sprint_tag(self) -> None:
        challenges = challenges_from_frame(
            pd.DataFrame(
                [
                    {
                        "challenge_id": "season_fm", "challenge_type": "marathon",
                        "challenge_name": "Season FM", "start_utc": "2026-09-01T00:00:00Z",
                        "end_utc": "2026-09-30T23:59:59Z", "bands": "FM",
                        "frequencies": "ALL", "active": "true",
                    },
                    {
                        "challenge_id": "sprint_945", "challenge_type": "sprint",
                        "challenge_name": "94.5 Sprint", "start_utc": "2026-09-05T00:00:00Z",
                        "end_utc": "2026-09-06T23:59:59Z", "bands": "FM",
                        "frequencies": "94.5", "propagation_modes": "Tropo", "active": "true",
                    },
                ]
            ).fillna("")
        )
        log = {
            "band": "FM", "frequency": 94.5, "station_country": "United States",
            "station_region": "TX", "distance_miles": 300,
            "reception_utc": "2026-09-05T12:00:00Z", "propagation": "Tropo",
        }
        valid, _, sprint_names = validate_season_submission(
            log, challenges, datetime(2026, 9, 6, tzinfo=timezone.utc)
        )
        self.assertTrue(valid)
        self.assertEqual(sprint_names, ["94.5 Sprint"])
        valid, message, _ = validate_season_submission(
            {**log, "reception_utc": "2026-10-01T00:00:00Z"},
            challenges,
            datetime(2026, 10, 2, tzinfo=timezone.utc),
        )
        self.assertFalse(valid)
        self.assertIn("outside", message)
        valid, message, _ = validate_season_submission(
            {**log, "reception_utc": "2026-09-07T00:00:00Z"},
            challenges,
            datetime(2026, 9, 6, tzinfo=timezone.utc),
        )
        self.assertFalse(valid)
        self.assertIn("future", message)

    def test_display_preferences_convert_without_changing_canonical_values(self) -> None:
        preferences = {
            "time_display": "Local time", "timezone_name": "America/Chicago",
            "clock_format": "12-hour", "distance_unit": "Kilometers",
        }
        self.assertEqual(
            format_reception("2026-09-05T12:00:00Z", preferences),
            "2026-09-05 07:00 AM CDT",
        )
        self.assertAlmostEqual(convert_distance(100, preferences), 160.9344)

    def test_mw_combined_propagation_and_daypart_match_challenge_rules(self) -> None:
        frame = pd.DataFrame(
            [
                {
                    "challenge_id": "mw_night",
                    "challenge_type": "sprint",
                    "challenge_name": "MW night",
                    "start_utc": "2026-09-01T00:00:00Z",
                    "end_utc": "2026-09-30T23:59:59Z",
                    "bands": "MW",
                    "frequencies": "910",
                    "propagation_modes": "Skywave",
                    "dayparts": "Nighttime",
                    "active": "true",
                }
            ]
        ).fillna("")
        challenge = challenges_from_frame(frame)[0]
        log = {
            "band": "MW",
            "frequency": 910,
            "station_country": "United States",
            "station_region": "TX",
            "distance_miles": 400,
            "reception_utc": "2026-09-10T07:00:00Z",
            "propagation": "Skywave / Nighttime",
            "source": "bulk_import",
        }
        self.assertEqual(canonical_propagation(log["propagation"]), "Skywave")
        self.assertTrue(log_qualifies(log, challenge))

    def test_challenge_scoring_method_counts_unique_geography(self) -> None:
        rows = pd.DataFrame(
            {
                "user_id": ["a", "a", "a", "b"],
                "station_region": ["TX", "TX", "LA", "MS"],
                "station_id": ["1", "2", "3", "4"],
                "station_country": ["United States"] * 4,
                "station_grid": ["EM10", "EM20", "EM30", "EM40"],
                "station_county": ["A", "B", "C", "D"],
            }
        )
        scores = challenge_scores(rows, "Unique states/provinces").set_index("user_id")
        self.assertEqual(scores.loc["a", "score"], 2)

    def test_bandscan_history_uses_unique_station_count_and_distance_color(self) -> None:
        logs = pd.DataFrame(
            {
                "location_id": ["home", "home", "home", "home"],
                "band": ["FM", "FM", "FM", "FM"],
                "frequency": [94.5, 94.5, 94.5, 100.1],
                "station_id": ["a", "a", "b", "c"],
                "call": ["A", "A", "B", "C"],
                "station_city": ["One", "One", "Two", "Three"],
                "station_region": ["LA", "LA", "MS", "TX"],
                "distance_miles": [25, 25, 350, 500],
                "reception_utc": ["2026-09-01T00:00:00Z"] * 4,
            }
        )
        history = reception_history(logs, band="FM", location_id="home")
        self.assertEqual(history[94.5]["unique_stations"], 2)
        self.assertEqual(history[94.5]["interference"], "local")
        self.assertEqual(history[100.1]["interference"], "open")


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

    def test_shoutout_read_status_is_durable_and_reversible(self) -> None:
        updated, message = self.store.set_shoutout_read("40001", True)
        self.assertTrue(updated)
        self.assertIn("read on air", message)
        status = self.store.shoutout_statuses().set_index("entry_id").loc["40001"]
        self.assertEqual(status["read_on_air"], 1)
        self.assertTrue(status["read_utc"])
        sheet_row = self.store.sheet_row("Shoutout Status", "40001")
        self.assertEqual(sheet_row["read_on_air"], 1)

        updated, _ = self.store.set_shoutout_read("40001", False)
        self.assertTrue(updated)
        status = self.store.shoutout_statuses().set_index("entry_id").loc["40001"]
        self.assertEqual(status["read_on_air"], 0)
        self.assertEqual(status["read_utc"], "")

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

    def test_admin_can_correct_and_promote_an_unlisted_station(self) -> None:
        reception = datetime(2026, 9, 5, 2, 0, tzinfo=timezone.utc)
        payload = {
            **self._log(reception),
            "station_id": "unlisted_test",
            "frequency": 87.75,
            "call": "KTEST",
            "station_city": "Abilene",
            "station_review_status": "Pending",
            "source": "import_unlisted",
        }
        accepted, log_id = self.store.append_log(payload)
        self.assertTrue(accepted)
        updated, _ = self.store.admin_update_log(
            log_id,
            {
                "frequency": 87.7,
                "station_city": "Albany",
                "propagation": "Sporadic E",
            },
        )
        self.assertTrue(updated)
        corrected = self.store.logs(self.user_id).iloc[0]
        self.assertEqual(corrected["frequency"], 87.7)
        self.assertEqual(corrected["station_city"], "Albany")
        promoted, _, station_id = self.store.promote_station_override(log_id)
        self.assertTrue(promoted)
        self.assertEqual(station_id, "unlisted_test")
        self.assertEqual(len(self.store.station_overrides()), 1)
        self.assertTrue(self.store.station_review_logs().empty)

    def test_station_override_can_be_edited_and_reverted(self) -> None:
        accepted, log_id = self.store.append_log(
            self._log(datetime(2026, 9, 5, 3, 0, tzinfo=timezone.utc))
        )
        self.assertTrue(accepted)
        updated, _, station_id = self.store.upsert_station_override(
            {
                "station_id": "fm_example", "band": "FM", "frequency": 90.7,
                "call": "TEST-FM", "city": "New Orleans", "region": "LA",
                "country": "United States", "county": "Orleans", "grid": "",
                "latitude": 9.0, "longitude": -79.5, "source_log_id": "admin",
            }
        )
        self.assertTrue(updated)
        self.assertEqual(station_id, "fm_example")
        self.assertTrue(self.store.station_overrides().iloc[0]["grid"])
        corrected = self.store.logs(self.user_id).set_index("log_id").loc[log_id]
        self.assertEqual(corrected["call"], "TEST-FM")
        self.assertAlmostEqual(float(corrected["station_latitude"]), 9.0)
        self.assertAlmostEqual(float(corrected["station_longitude"]), -79.5)
        self.assertGreater(float(corrected["distance_miles"]), 1_000)
        self.assertEqual(int(corrected["revision"]), 2)
        with self.store.connect() as connection:
            connection.execute(
                "UPDATE logs SET station_latitude=7.0, station_longitude=81.0 WHERE log_id=?",
                (log_id,),
            )
        self.assertEqual(self.store.refresh_logs_from_station_overrides(), [log_id])
        reconciled = self.store.logs(self.user_id).set_index("log_id").loc[log_id]
        self.assertAlmostEqual(float(reconciled["station_longitude"]), -79.5)
        deleted, _ = self.store.delete_station_override(station_id)
        self.assertTrue(deleted)
        self.assertTrue(self.store.station_overrides().empty)

    def test_location_with_logs_is_locked_from_deletion(self) -> None:
        accepted, _ = self.store.append_log(self._log(datetime(2026, 9, 5, 2, 0, tzinfo=timezone.utc)))
        self.assertTrue(accepted)
        deleted, message = self.store.delete_location(self.user_id, self.location_id)
        self.assertFalse(deleted)
        self.assertIn("locked", message)

    def test_location_store_derives_grid_and_can_repair_geography(self) -> None:
        location_id = self.store.add_location(
            self.user_id,
            {
                "label": "City lookup",
                "city": "Baton Rouge",
                "region": "LA",
                "country": "United States",
                "grid": "",
                "latitude": 30.4515,
                "longitude": -91.1871,
                "is_home": False,
            },
        )
        before = self.store.locations(self.user_id).set_index("location_id").loc[location_id]
        self.assertEqual(before["grid"], latlon_to_grid(30.4515, -91.1871))
        updated, _ = self.store.update_location_geography(
            self.user_id,
            location_id,
            grid="EM40",
            latitude=30.5,
            longitude=-91.0,
        )
        self.assertTrue(updated)
        after = self.store.locations(self.user_id).set_index("location_id").loc[location_id]
        self.assertEqual(after["grid"], "EM40")
        self.assertAlmostEqual(float(after["latitude"]), 30.5)

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

    def test_admin_content_and_ticket_workflows_are_durable_locally(self) -> None:
        announcement_id = self.store.upsert_announcement(
            {"title": "Test", "body": "Message", "start_utc": "2026-09-01T00:00:00+00:00", "active": True}
        )
        self.assertIn(announcement_id, self.store.announcements()["announcement_id"].tolist())
        challenge_id = self.store.upsert_challenge(
            {
                "challenge_name": "Distance test",
                "challenge_type": "sprint",
                "timeframe_tag": "Week X",
                "start_utc": "2026-09-01T00:00:00+00:00",
                "end_utc": "2026-09-02T00:00:00+00:00",
                "bands": "FM",
                "frequencies": "ALL",
                "min_distance": "500",
                "scoring_method": "Unique stations",
                "active": True,
            }
        )
        self.assertIn(challenge_id, self.store.challenges()["challenge_id"].tolist())
        ticket_id = self.store.create_support_ticket(
            self.user_id, "Feature request", "Add this", "Details"
        )
        updated, _ = self.store.update_support_ticket(
            ticket_id, status="In progress", admin_comment="Reviewing it now."
        )
        self.assertTrue(updated)
        ticket = self.store.support_tickets(self.user_id).iloc[0]
        self.assertEqual(ticket["status"], "In progress")
        self.assertEqual(ticket["admin_comment"], "Reviewing it now.")


if __name__ == "__main__":
    unittest.main()
