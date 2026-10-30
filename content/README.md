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
- `min_distance` and `max_distance`: Optional inclusive distance limits in miles.
- `min_night_power_kw`: Optional inclusive nighttime transmitter-power minimum in
  kilowatts for MW-only sprints. Enter `20` for at least 20 kW. Leave blank to
  ignore power. The domestic source's PWR_N is converted from watts; daytime
  power is never substituted. Unknown nighttime power is excluded when enabled.
  This field does not restrict reception time; select `Skywave / Nighttime` in
  propagation/daypart settings separately if required. Other station lists may
  lack nighttime power, so their records remain unknown until power is supplied.
- `night_power_allowance_kw`: Optional allowance subtracted from the nighttime
  baseline, defaulting to `0`. With a `20` baseline and `1` allowance, the inclusive
  qualifying cutoff is `19` kW. Use `0.5` for a `19.5` kW cutoff instead. The
  allowance cannot be negative or exceed the baseline, and requires a power
  baseline when nonzero. Unknown nighttime power stays excluded.
- `propagation_modes`: Optional modes separated with `|`. Supported MW values are
  `Groundwave / Daytime`, `Sunrise grayline`, `Sunset grayline`, and
  `Skywave / Nighttime`; FM/NWR propagation modes may be mixed into the same field.
- `dayparts`: Legacy MW daypart field retained for older schedules. New challenges
  should use `propagation_modes`; the Admin page maintains compatibility automatically.
- `scoring_method`: `Unique stations`, `Total logs`, `Unique states/provinces`,
  `Unique countries`, `Unique grids`, or `Unique counties`.
- `station_eligibility`: `All stations` (the default for blank/missing values) or
  `New this season only`. The latter is available for sprints with `Unique stations`
  scoring. A DXer's first reception meeting the enabled season marathon criteria
  must fall within the sprint window. All operating locations and entry methods
  participate in this check. Older receptions uploaded later recalculate results.
- `description`: Public explanation of the challenge.
- `active`: `true` enables the row; `false` keeps it as a draft.

Leave a restriction field blank to allow all values. Sprint rules never prevent
ordinary logging. A DXer may opt into a sprint filter on Log Entry, while the results
pages independently enforce every sprint rule when calculating challenge scores.

Enabled `marathon` rows define season-long eligibility. Home progress, Awards, and
Season leaders count a reception only when it satisfies at least one enabled marathon's
date window, band, frequency, geography, distance, propagation, and daypart rules.
Changing a marathon in Admin recalculates those views without deleting historical logs.

For an all-band new-stations sprint, choose **Admin → Challenges → Add new challenge**,
set the type to **sprint**, select **MW, FM, NWR**, enter **ALL** for frequencies,
set the UTC start/end, choose **New this season only** under **Station eligibility**,
and use **Unique stations** leaderboard scoring. Leave the other restrictions blank
for an unrestricted event, enable the challenge, and save. Repeat receptions remain
available to the normal season log but score only once for the sprint. The app
automatically adds the new field to the environment's Challenges Sheet; do not
manually edit Sheet headers or change Secrets.

For a Blowtorch sprint, select **MW** only, enter **ALL** for frequencies and **20**
for **Minimum nighttime power (kW)**, and choose the UTC window and leaderboard
scoring. To include stations within 1 kW below that baseline, enter **1** for
**Nighttime power allowance (kW)**; the effective cutoff becomes **19 kW**.
Leave **Station eligibility** at **All stations** unless the event also
requires new seasonal stations. Set **Skywave / Nighttime** only if the receptions
themselves must occur at night; leaving propagation/daypart blank allows any daypart.

## `shoutouts_source.txt`

Store the single published-to-web CSV URL for the WPForms shoutout response Sheet.
Community refreshes this source about every five minutes and keeps only the public
name, broad location, category, details, aircheck, and submission-date columns.
Replace the URL here if the published Google Sheet changes; no secret is required.

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
