# Season content files

These files are designed to be edited directly in GitHub. Saving a commit causes
Streamlit Community Cloud to redeploy and use the revised content.

## `announcements.csv`

Add one row per announcement.

- `announcement_id`: Short unique ID; do not reuse an old ID.
- `title`: Heading shown on Home.
- `message`: Announcement text. Put quotation marks around text containing commas.
- `start_utc`: Optional scheduled publication time, for example `2026-09-01T14:00:00Z`.
- `end_utc`: Optional expiration time. Leave blank to keep it visible.
- `active`: `true` shows the announcement; `false` hides it without deleting it.

## `challenge_schedule.csv`

Add one row per season-long or weekly challenge. Times are always UTC.

- `challenge_id`: Short unique ID.
- `challenge_type`: `marathon` for season-long or `sprint` for a weekly challenge.
- `challenge_name`: Public name.
- `timeframe_tag`: Short label for exports and analysis.
- `start_utc` and `end_utc`: ISO UTC timestamps ending in `Z`.
- `bands`: `MW`, `FM`, `NWR`, or multiple bands separated with `|`.
- `frequencies`: `ALL`, one frequency such as `910`, a range such as `88.1-107.9`,
  or multiple values/ranges separated with `|`.
- `include_countries`: Optional country allow-list separated with `|`.
- `exclude_countries`: Optional country block-list separated with `|`.
- `propagation_modes`: Optional FM/NWR modes separated with `|`.
- `dayparts`: Optional MW automatic modes separated with `|`. Supported values are
  `Daytime`, `Sunrise grayline`, `Sunset grayline`, and `Nighttime`.
- `description`: Public explanation of the challenge.
- `active`: `true` enables the row; `false` keeps it as a draft.

Leave a restriction field blank to allow all values. If a sprint is active for one
band, only that band is restricted; normal logging remains open on the other bands.

## `support_email.txt`

Replace `support@example.com` with the inbox that should receive support requests.
The support form prepares a pre-addressed email in the DXer's own email application;
the app never stores an email password or sends mail silently.
