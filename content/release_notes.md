### Version 1.0.0-rc7 · Seventh-round testing

- Corrected custom-import timestamp detection so Google Form submission timestamps are not mistaken for reception timestamps; local date/time fields now convert using the DXer's confirmed timezone.
- Added every MW daypart—Sunrise, Daytime, Sunset, and Nighttime—to challenge rules, logging, imports, and reception editing.
- Added an All frequencies station search, full-filter match totals, and a performance-safe nearest-results display.
- Expanded the administrator review queue with reception timestamps, grouped repeat reports, canonical corrections, and direct promotion into a private managed station database.
- Added direct Home award links and interactive Bandscan distance filters with one-click clearing.

### Version 1.0.0-rc6 · Sixth-round testing

- Expanded Current and Previous challenge results into a full challenge-specific analytics dashboard with all-DXer counters, selectable DXer tables, maps, paths, filters, and qualifying receptions.
- Moved challenge results off the general Leaderboards page; added filterable season and season-to-date sprint leaderboards.
- Made the active-challenge station-list filter move directly to the selected challenge frequency while leaving normal and bulk logging unrestricted.
- Made MW propagation/daypart editable during review and added Sunrise grayline and Sunset grayline options alongside Daytime and Nighttime.
- Changed Bandscan distance colors to high-contrast red, orange, and green outlines.
- Added an explicit Google Sheet retry path for locally retained writes and clarified transient sync status.
- Removed the inactive Community opt-in badge until individual sharing is implemented.

### Version 1.0.0-rc5.1 · Location lookup correction

- City/state/province lookups now validate and store latitude, longitude, and a calculated 6-character Maidenhead grid before the location is created.
- Location-save confirmation displays the exact calculated grid and coordinates.
- Profile settings identifies previously saved incomplete locations and provides a repair action that also synchronizes the corrected geography to the private Google Sheet.

### Version 1.0.0-rc5 · Fifth-round testing

- Reworked Bandscan into a read-only reception-history view with unique-station counts, distance-based channel colors, and detailed station/date/time/propagation history.
- Removed the bandscan prerequisite so all bands and frequencies remain available for season-long logging.
- Made active-challenge station filtering optional while preserving strict criteria for final challenge scoring.
- Added a protected administration portal for announcements, challenge scheduling, support responses, and unlisted-station review.
- Added Feature requests and in-app ticket status/latest-response visibility.
- Moved all display palettes to Profile settings and strengthened light, dark, and high-contrast widget styling.
- Added an importer resolution workflow: suggested matches require confirmation, while approved unlisted stations remain flagged for administrator review.

### Version 1.0.0-rc4 · Fourth-round testing

- Added the reviewed bulk-import workflow for FMList, MWList, WLogger, and mapped CSV/XLSX files.
- Enabled guarded private Google Sheet mirroring while retaining fast local reads and calculations.
- Added the Season 7 logo, version label, release notes, and privacy information.
- Expanded My logbook filters and added one-click filter resets throughout the logging workflow.
- Added band-specific safeguards before the remaining bandscan channels can be filled OPEN.
- Fixed county-map selection so a click filters the reception table once without entering a refresh loop.
- Kept display names attached to the stable signed-in account so historical logs, awards, and leaderboards follow a name change.

### Version 1.0.0-rc3 · Third-round testing

- Added editable display names, additional themes, high contrast, guided help, and support-ticket preparation.
- Added file-managed announcements and challenge scheduling.
- Added grid-square and county maps, transmitter-county cleanup, filter resets, and band-colored path/station maps.
