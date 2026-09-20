### Version 1.0.0-rc10.13 · Station intelligence and map overlays

- Added WTFDA format and station-slogan data to FM station-list rows and Station map hover details.
- Added a current grayline overlay as the Station map default, with separate daylight, approximate ±6° twilight, and darkness shading plus an on-demand refresh control.
- Added selectable heard/unheard progress overlays for U.S./Canadian/Mexican states and provinces, worldwide 4-character Maidenhead grids, U.S. counties/parishes, and countries or territories; each uses season-scoped logs from the selected band.
- Added default-on station call labels beside map markers and the DXer's last-heard timestamp to station hover details.
- Kept every overlay and label layer non-interactive so station markers remain the sole click target for opening the reception review form.

### Version 1.0.0-rc10.12 · North American map boundaries

- Added U.S. state, Canadian province/territory, and Mexican state borders to the interactive Station map on Log Entry.
- Kept the boundary layer non-interactive so hover and click behavior remains reserved for station markers.
- Adapted boundary contrast to the DXer's selected light or dark display theme while preserving the existing logged/unlogged marker colors.

### Version 1.0.0-rc10.11 · Interactive station map logging

- Added a Station map entry method that plots every database station on the selected MW, FM, or NWR frequency, including U.S., Canadian, and international records.
- Added accessible orange and cyan marker states for new and previously logged stations, with full station-list details available on hover.
- Made a station-marker click open the existing Live DX / From recording review form, preserving the same validation, sticky settings, duplicate protection, and final confirmation used by Station list.

### Version 1.0.0-rc10.10 · MW station coverage reconciliation

- Added 48 active Canadian MW calls that were missing from the managed station list, using transmitter coordinates returned by AM DXer's station-detail lookup.
- Corrected the current frequencies and transmitter records for CHED, CKNW, and CHIN, and removed the deleted CHQT service from the selectable station list.
- Added the independently verified current U.S. omissions KCIK 740 and WSAT 1280, including transmitter county and FIPS data for filters, awards, and maps.
- Kept cancelled or defunct source-only U.S. facilities out of the active 2026 station selector rather than reintroducing stale records.

### Version 1.0.0-rc10.9 · MW identification details

- Enriched the existing U.S. and Canadian MW station records with format, network/slogan, FM parallel, former-call, relay, and other identification notes provided by Tim Tromp.
- Added Format, Network / slogan, and FM //s / notes columns to the MW station list on Log Entry, with the station call pinned while DXers scroll through the added details.
- Used strict frequency/call matching plus two verified call-history aliases; unmatched existing stations remain available with blank identification fields rather than receiving uncertain metadata.

### Version 1.0.0-rc10.8 · 92.9 MHz station database correction

- Rebuilt the complete 92.9 MHz section from the current WTFDA export, restoring 66 legitimate stations that had been displaced by duplicate records during the earlier enrichment process.
- Converted all WTFDA latitude and longitude values from degree-minute-second notation to signed decimal coordinates for station searches, distance calculations, path maps, and station-location maps.
- Restored unique station IDs across all 317 records and populated county data for every U.S. 92.9 MHz transmitter location.

### Version 1.0.0-rc10.7 · Recording timestamp memory

- Made both the UTC date and UTC time remain in place after a successful From recording submission, speeding up entry of multiple stations heard in the same recording.
- Kept Live DX tied to the current UTC timestamp and prevented rejected duplicate submissions from replacing the last successfully used recording timestamp.

### Version 1.0.0-rc10.6 · Privacy and AI transparency

- Replaced the short disclaimer with a detailed privacy policy explaining the information collected, how it is used, what other participants can see, service providers, security, retention, user choices, and support requests.
- Added a prominent Privacy & transparency card near the top of Community with clear no-password and no-data-sale statements.
- Added an explicit disclosure that The DX Challenge was coded with generative-AI assistance under human direction while the deployed App does not send participant records to an AI model.

### Version 1.0.0-rc10.5.1 · Community guide hotfix

- Made the Community page's user-guide link self-contained so the page remains compatible during staggered or partial GitHub deployments.

### Version 1.0.0-rc10.5 · User guide access

- Added a prominent Community-page button that opens the complete illustrated Version 1.0 user guide directly from its permanent GitHub release URL.

### Version 1.0.0-rc10.4 · Challenge environment isolation

- Keyed the cached Google Sheet connection by environment, Sheet ID, write setting, and service-account identity so a deployment can never retain a client created from another Secrets configuration.
- Added a hard safety block preventing the known staging and production Sheet IDs from being crossed.
- Made each environment's nonempty Challenges, Announcements, and Station Overrides tabs replace cached configuration during startup, removing stale configuration inherited before this fix.
- Made the Admin portal show the exact environment and Sheet suffix targeted by each challenge save.

### Version 1.0.0-rc10.3 · Dual-environment sync resilience

- Reduced Google Sheets startup requests by reusing one worksheet index and one header/data read per managed tab, avoiding quota collisions when staging and production restart together.
- Stopped rewriting an unchanged authenticated user on every Streamlit interaction.
- Made Retry Google Sheet sync resume an interrupted startup hydration instead of performing only a user-record write.

### Version 1.0.0-rc10.2 · Production isolation hotfix

- Made the production Google Sheet authoritative during startup, including intentionally empty tabs, so cleared beta records cannot survive in or be restored from the fast local cache.
- Preserved staging's safe tab-seeding behavior for demonstrations and schema upgrades while keeping its cache and Google Sheet isolated from production.

### Version 1.0.0-rc10.1 · Station correction and map hotfix

- Made administrator station-database corrections cascade into existing reception records, including corrected coordinates, grid, station details, and recalculated QTH distance; the repaired records are mirrored back to Google Sheets.
- Added an automatic startup reconciliation so overrides saved before this hotfix repair their associated logs on the first deployment launch.
- Normalized mixed Google Sheet coordinate values before rendering Station locations and Paths, preventing the all-band float/string map crash in both Stats and challenge analysis.

### Version 1.0.0-rc10 · Final beta safeguards and preferences

- Enforced one authoritative reception boundary at final save: every entry must qualify for an enabled Season 7 marathon, future timestamps are rejected, and qualifying weekly sprints are classified independently using their full rules.
- Applied the same season scope to previously-heard station indicators and Bandscan reception history.
- Added an IANA time-zone selector for local-time imports, clearer unlisted-station approval, and durable Pending Logs that can be resolved later without uploading the file again.
- Added administrator-managed station database corrections without modifying the licensed source files.
- Added profile choices for UTC or local-time display, 24- or 12-hour clocks, and miles or kilometers while retaining canonical UTC/miles storage.

### Version 1.0.0-rc9.1 · Season scope, achievements, and environment split

- Made My Logbook, its personal export, and every Stats view use the same enabled Season 7 marathon boundary as Awards and season leaderboards; imported out-of-season archive logs remain stored but excluded.
- Added an administrator-only, durable read-on-air control and read/unread filter for Community shoutouts plus a public Read on air badge.
- Added uploaded-media filenames beside shoutout attachment buttons.
- Replaced Livestream prompts with Achievement Corner, driven by actual award qualifications and endorsement thresholds.
- Made the app environment label and private Google Sheet selectable through Streamlit Secrets so staging data can remain intact while production starts clean.

### Version 1.0.0-rc9 · Ninth-round challenge mechanics

- Made enabled Admin-managed marathon rules authoritative for Home season progress, Awards, and Season leaders; out-of-window logs remain safely stored but no longer count.
- Corrected the published shoutout date protocol to UTC `DD/MM/YYYY` and replaced the long feed with a one-at-a-time previous/next carousel.
- Added zoomable Canadian province/territory and Mexican state choropleth maps to Stats and challenge analysis.
- Added canonical Canada/Mexico subdivision matching for country codes, abbreviations, full names, and accented source-list variants.

### Version 1.0.0-rc8.1 · Live Community shoutout feed

- Connected Community directly to the published Season 7 shoutout CSV with a five-minute background-refresh cache.
- Added the revised Submission Date and aircheck-upload headers so month filtering and media links activate automatically.
- Kept the service-account/private-Sheet connection available as an optional fallback.

### Version 1.0.0-rc8 · Eighth-round testing

- Made announcement expiration dates and times editable immediately after No expiration is unchecked.
- Corrected Bandscan distance-filter clearing so every band returns safely to All.
- Made the active-challenge filter restrict the frequency selector to eligible channels and start at the challenge's lowest frequency.
- Defined the four MW solar dayparts and made bulk imports calculate them from reception time, date, and operating QTH.
- Added a newest-first Community shoutout feed with DXer, category, and optional submission-month filters plus attachment links.

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
