# Season content files

These files seed a brand-new installation. After the app has created its private
Google Sheet tables, manage announcements and challenges from the protected **Admin**
page so changes are durable and take effect without a GitHub redeploy.

## `announcements.csv`

Seed one row per announcement. Use **Admin → Announcements** for deployed changes.

- `announcement_id`: Short unique ID; do not reuse an old ID.
- `title`: Heading shown on Home.
- `message`: Announcement text. Put quotation marks around text containing commas.
- `start_utc`: Optional scheduled publication time, for example `2026-09-01T14:00:00Z`.
- `end_utc`: Optional expiration time. Leave blank to keep it visible.
- `active`: `true` shows the announcement; `false` hides it without deleting it.

## `challenge_schedule.csv`

Seed one row per season-long or weekly challenge. Use **Admin → Challenges** for
deployed changes. Times are always UTC.

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
- `include_regions` and `exclude_regions`: Optional state/province allow- and
  block-lists separated with `|`.
- `min_distance_miles` and `max_distance_miles`: Optional inclusive distance limits.
- `propagation_modes`: Optional FM/NWR modes separated with `|`.
- `dayparts`: Optional MW automatic modes separated with `|`. Supported values are
  `Daytime`, `Sunrise grayline`, `Sunset grayline`, and `Nighttime`.
- `scoring_method`: `Unique stations`, `Total logs`, `Unique states/provinces`,
  `Unique countries`, `Unique grids`, or `Unique counties`.
- `description`: Public explanation of the challenge.
- `active`: `true` enables the row; `false` keeps it as a draft.

Leave a restriction field blank to allow all values. Active challenges never prevent
ordinary season logging. A DXer may opt into a challenge filter on Log Entry, while
the results pages independently enforce every rule when calculating challenge scores.

## `support_email.txt`

Replace `support@example.com` with the inbox that should receive support requests.
The support form prepares a pre-addressed email in the DXer's own email application;
the app never stores an email password or sends mail silently.

## `release_notes.md`

Add the newest version heading and bullet list at the top. This file appears on
Community exactly as Markdown, so no Python changes are needed for routine release
notes. Keep the version label in `dxcore/config.py` synchronized with the newest
heading when promoting a build.

## `privacy_policy.md`

This Markdown file appears under Privacy policy and disclaimer on Community. Update
it whenever sign-in scopes, stored data, public visibility, retention, or user
controls materially change. It must describe what the deployed code actually does.
