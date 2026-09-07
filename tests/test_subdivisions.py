import unittest

import pandas as pd

from dxcore.subdivisions import add_subdivision_keys, subdivision_counts, subdivision_geojson


class SubdivisionTests(unittest.TestCase):
    def test_canadian_abbreviation_and_country_code_are_normalized(self) -> None:
        logs = pd.DataFrame(
            [
                {"station_country": "Canada", "station_region": "ON"},
                {"station_country": "CAN", "station_region": "Ontario"},
                {"station_country": "Mexico", "station_region": "Ontario"},
            ]
        )
        result = add_subdivision_keys(logs, "CAN")
        self.assertEqual(result["admin1_code"].tolist(), ["CA-ON", "CA-ON"])

    def test_mexican_mojibake_and_city_aliases_are_normalized(self) -> None:
        logs = pd.DataFrame(
            [
                {"station_country": "MEX", "station_region": "Estado de M\ufffdxico"},
                {"station_country": "Mexico", "station_region": "Ciudad Mexico"},
            ]
        )
        result = add_subdivision_keys(logs, "MEX")
        self.assertEqual(result["admin1_code"].tolist(), ["MX-MEX", "MX-DIF"])

    def test_counts_include_zero_regions_for_a_complete_choropleth(self) -> None:
        logs = pd.DataFrame(
            [{"station_country": "Canada", "station_region": "AB"}]
        )
        counts = subdivision_counts(logs, "CAN", "Unique logs")
        self.assertEqual(int(counts.loc[counts["admin1_code"] == "CA-AB", "Unique logs"].iloc[0]), 1)
        self.assertEqual(len(counts), 13)
        self.assertEqual(len(subdivision_geojson("MEX")["features"]), 32)


if __name__ == "__main__":
    unittest.main()
