import unittest

import pandas as pd

from dxcore.shoutouts import (
    CATEGORY_HEADER,
    media_filename,
    normalize_shoutouts,
    observed_categories,
)


class ShoutoutTests(unittest.TestCase):
    def test_uploaded_media_filename_is_decoded_without_query_string(self) -> None:
        self.assertEqual(
            media_filename("https://example.com/uploads/My%20DX%20Clip.mp3?download=1"),
            "My DX Clip.mp3",
        )

    def test_wpforms_export_is_newest_first_and_keeps_public_columns_only(self) -> None:
        source = pd.DataFrame(
            [
                {
                    "Entry ID": "31499",
                    "Name": "SkywaveBirdDX",
                    "State/Province/Region": "CA",
                    "Country": "USA",
                    CATEGORY_HEADER: "New Log\nNew Country",
                    "ShoutOut Details": "First foreign TV DX.",
                    "Upload?": "",
                    "Email": "private@example.com",
                },
                {
                    "Entry ID": "31567",
                    "Name": "Stuart, W8SRC",
                    "State/Province/Region": "Michigan",
                    "Country": "United States",
                    CATEGORY_HEADER: (
                        "New Log\nSomething Else (break a distance record, add some new gear, "
                        "learn a new skill, etc..)"
                    ),
                    "ShoutOut Details": "Several new catches.",
                    "Upload?": "https://example.com/clip.mp3",
                    "Email": "also-private@example.com",
                },
            ]
        )
        result = normalize_shoutouts(source)
        self.assertEqual(result["entry_id"].tolist(), ["31567", "31499"])
        self.assertNotIn("Email", result.columns)
        self.assertEqual(len(result.iloc[0]["categories"]), 2)
        self.assertIn("New Country", observed_categories(result))

    def test_submission_month_activates_when_timestamp_exists(self) -> None:
        source = pd.DataFrame(
            [
                {
                    "Entry ID": "1",
                    "Name": "DXer",
                    CATEGORY_HEADER: "New Log",
                    "ShoutOut Details": "A catch",
                    "Timestamp": "2026-03-15 20:00:00",
                }
            ]
        )
        result = normalize_shoutouts(source)
        self.assertEqual(str(result.iloc[0]["submission_month"]), "2026-03")

    def test_season_seven_headers_enable_airchecks_and_submission_month(self) -> None:
        source = pd.DataFrame(
            [
                {
                    "Entry ID": "40001",
                    "Name": "DXer",
                    "State/Province/Region": "LA",
                    "Country": "United States",
                    CATEGORY_HEADER: "New Louisiana Station Log",
                    "ShoutOut Details": "A new local catch.",
                    "Do You Have an Aircheck You Want to Share?": "https://example.com/catch.mp3",
                    "Submission Date": "02/09/2026 20:15",
                }
            ]
        )
        result = normalize_shoutouts(source)
        self.assertEqual(result.iloc[0]["upload_url"], "https://example.com/catch.mp3")
        self.assertEqual(str(result.iloc[0]["submission_month"]), "2026-09")
        self.assertEqual(result.iloc[0]["submitted_at"].day, 2)
        self.assertEqual(str(result.iloc[0]["submitted_at"].tz), "UTC")


if __name__ == "__main__":
    unittest.main()
