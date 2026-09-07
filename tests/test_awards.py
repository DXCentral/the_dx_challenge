from __future__ import annotations

import unittest

import pandas as pd

from dxcore.awards import award_milestones


class AwardMilestoneTests(unittest.TestCase):
    def test_international_award_and_endorsement_use_first_crossing_dates(self) -> None:
        start = pd.Timestamp("2026-09-01T00:00:00Z")
        logs = pd.DataFrame(
            [
                {
                    "user_id": "dxer-1",
                    "band": "MW",
                    "frequency": 900 + index,
                    "station_id": f"mw-{index}",
                    "station_region": "",
                    "station_country": f"Country {index}",
                    "station_county": "",
                    "station_grid": "",
                    "reception_utc": start + pd.Timedelta(hours=index),
                    "propagation": "Nighttime",
                    "source": "station_list",
                    "distance_miles": 1000,
                }
                for index in range(25)
            ]
        )
        result = award_milestones(logs, {"dxer-1": "KDX"})
        international = result[result["award"] == "MW · International DXer"].sort_values(
            "achieved_utc"
        )
        self.assertEqual(len(international), 2)
        self.assertEqual(international.iloc[0]["milestone"], "MW · International DXer")
        self.assertIn("25 endorsement", international.iloc[1]["milestone"])
        self.assertEqual(international.iloc[1]["dxer"], "KDX")

    def test_propagation_master_requires_every_component(self) -> None:
        modes = ["Tropo", "Meteor Scatter", "Sporadic E"]
        logs = pd.DataFrame(
            [
                {
                    "user_id": "dxer-2",
                    "band": "NWR",
                    "frequency": 162.4 + index / 1000,
                    "station_id": f"nwr-{mode}-{index}",
                    "station_region": "LA",
                    "station_country": "United States",
                    "station_county": "Test",
                    "station_grid": "EM40",
                    "reception_utc": pd.Timestamp("2026-09-01T00:00:00Z")
                    + pd.Timedelta(hours=offset * 5 + index),
                    "propagation": mode,
                    "source": "station_list",
                    "distance_miles": 200,
                }
                for offset, mode in enumerate(modes)
                for index in range(5)
            ]
        )
        result = award_milestones(logs, {"dxer-2": "WeatherDX"})
        event = result[result["award"] == "NWR · Propagation Master"].iloc[0]
        self.assertEqual(event["milestone"], "NWR · Propagation Master qualified")
        self.assertIn("Sporadic E 5/5", event["summary"])


if __name__ == "__main__":
    unittest.main()
