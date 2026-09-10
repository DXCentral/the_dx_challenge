# The DX Challenge Privacy Policy

**Effective date:** September 8, 2026  
**Last updated:** September 8, 2026

## 1. Scope and operator

This Privacy Policy explains how DX Central ("DX Central," "we," "us," or "our") collects, uses, stores, and shares information through The DX Challenge application, including its production and staging/testing environments (the "App"). The App is a non-commercial radio-listening challenge platform used to record receptions, calculate challenge results and awards, and share community statistics.

## 2. Information we collect

### Google sign-in information

The App uses Google as an OpenID Connect identity provider. When you sign in, the App receives the stable account identifier, email address, and name supplied in Google's identity response. We use these fields to create and recover the correct DX Challenge profile and to keep each participant's records separate.

The App does **not** receive or store your Google password. It does not request access to your Gmail, contacts, Google Drive files, calendar, or other unrelated Google account content.

### Profile and preference information

We store the display name you choose and App preferences such as theme, accessibility settings, time zone, UTC/local-time display, clock format, distance units, and whether the introductory walkthrough has been completed.

### Receiving locations

For each Home or alternate/portable QTH you create, we store the location label, city, state/province or region, country, Maidenhead grid square, latitude, longitude, Home-QTH status, and creation date. These details are necessary to sort station choices by distance, calculate paths and distances, determine MW dayparts, and produce geographic statistics.

### Reception, bandscan, and challenge information

We store the reception information you submit, including the station, band, frequency, reception date and time, propagation/daypart, station geography, calculated distance, SDR and portable-operation selections, notes, submission source, challenge classification, and record history. Bandscan activity and station-review status may also be retained. Stable record identifiers, timestamps, revision information, and deletion status are used to synchronize records and prevent accidental duplicates.

### Bulk-import information

When you use a bulk importer, we process the file you select and store information needed to review and normalize its entries. This may include the uploaded filename, source format, date/time protocol, selected time zone, row totals, imported row content, normalized values, matching decisions, and review status. The App does not intentionally retain the original binary upload after processing, but imported row content and import-review records may remain in challenge storage. Remove unrelated or sensitive columns before uploading a file.

### Support and feature requests

If you submit a support ticket or feature request, we store its category, subject, description, status, timestamps, and administrator response with your account identifier. If you choose to open your email application from the support area, your email provider handles that message under its own terms.

### Community shoutouts

Community shoutouts come from a separately published DX Central submission feed. The Community page may display the participant-provided name, broad location, categories, description, submission date, optional media filename/link, and whether the shoutout has been read on air. Shoutouts are intended for public or community recognition; do not include anything you do not want shared. The App discards response-feed columns that are not used by the Community display.

### Authentication cookies and service data

Streamlit uses an identity cookie to keep you signed in. If you close the App without logging out, that cookie may remain in your browser for up to 30 days. Signing out of the App removes the App identity cookie but does not sign you out of Google.

Streamlit Community Cloud, Google, and other infrastructure providers may process routine technical information such as IP addresses, browser/device details, timestamps, and error or security logs under their own privacy notices. DX Central has not added advertising trackers or third-party behavioral advertising to the App.

## 3. How we use information

We use information collected through the App to:

- authenticate users and maintain individual profiles;
- save, retrieve, validate, deduplicate, edit, delete, and export reception records;
- calculate station distance, paths, dayparts, statistics, maps, leaderboards, awards, and challenge eligibility;
- normalize bulk imports and review stations not found in the supplied station databases;
- operate Home, Bandscan, Log entry, My logbook, Challenges, Awards, Leaderboards, Stats, Community, Profile settings, and administrator features;
- provide technical support, respond to feature requests, correct station data, and maintain challenge integrity;
- diagnose failures, protect the App and its participants, and comply with lawful obligations; and
- improve the App's reliability, usability, accessibility, and challenge rules.

We do not sell or rent participant personal information. We do not use it for targeted advertising or unrelated commercial marketing.

## 4. What other participants can see

Authenticated participants may see your chosen display name together with qualifying reception details, station information, reception date/time, propagation mode, notes, scores, award progress, challenge results, and aggregated statistics.

Standard tables do not intentionally display your email address or Google account identifier. However, path maps use the receiving coordinates attached to a log. A map may therefore display, or allow another participant to infer, the approximate or precise geographic location from which a reception was made. Use a suitably broad location or Maidenhead grid center if you do not want to associate an exact address-level point with your activity. Never enter a private address in a public-facing label or reception note.

Your protected My logbook export contains only your submitted logs. It does not provide a downloadable copy of the proprietary station lists. Community shoutouts and linked media may be accessible outside the authenticated App through the separately published submission source or the linked media host.

## 5. When information is shared

We share information only as needed to operate the App:

- **Streamlit Community Cloud / Snowflake** hosts and runs the App.
- **Google Identity** authenticates your Google account.
- **Google Sheets and Google Cloud service accounts** provide private, environment-specific durable storage and synchronization.
- **GitHub** hosts public App code, documentation, and selected static resources; account records and private challenge Sheets are not intentionally published to the repository.
- **Shoutout form, spreadsheet, and media providers** process voluntary Community submissions and attachments under their own terms.
- **DX Central administrators** may access account, location, reception, import-review, support, and configuration records as needed to operate and moderate the challenge.

We may preserve or disclose information when reasonably necessary to comply with law or legal process; protect the rights, safety, or security of DX Central, participants, or others; investigate abuse; or maintain the integrity of challenge results. We do not otherwise disclose personal information to unrelated third parties for their own marketing.

## 6. Storage and security

Durable challenge records are stored in private Google Sheets controlled by DX Central and accessed through restricted service-account credentials. Production and staging use separate Sheets. The App may also use a server-side local cache to keep the interface responsive and temporarily retain changes during a synchronization interruption.

We use reasonable administrative and technical safeguards, including authenticated access, private data stores, restricted service-account credentials, and secret management. No internet service or storage system can be guaranteed completely secure, and we cannot promise that unauthorized access, loss, or interruption will never occur.

## 7. Retention and deletion

Account, profile, location, log, import-review, and support records may be retained for the active season and afterward as reasonably needed to maintain historical challenge results, resolve disputes, prevent duplicate or conflicting records, support the App, and meet legal or security needs. The App does not currently apply one automatic deletion date to every record type.

When you delete a reception, it disappears from your active logbook and challenge calculations. Its underlying stable record, submitted values, and deletion timestamp may remain in private storage so synchronization does not recreate it and challenge history remains auditable. Locations associated with active logs cannot be deleted through the interface until those dependencies are resolved.

Service providers may retain backups or technical logs for their own limited retention periods. Removing Google access or signing out does not automatically delete information already stored by The DX Challenge. To request review, correction, or deletion of account-related information, submit a Privacy/support ticket from **Profile settings → Help & support**. Some information may be retained when necessary for security, legal compliance, or the integrity of completed challenge results.

## 8. Your choices

Depending on the record and challenge status, the App allows you to:

- change your display name and display/accessibility preferences;
- create and select Home or portable receiving locations;
- edit or delete your own reception records;
- export your own eligible logbook records;
- choose whether to submit a public Community shoutout or linked media; and
- ask DX Central to review, correct, or delete account-related information through an in-App ticket.

Please keep your information accurate and avoid submitting another person's personal information without permission.

## 9. AI-assisted development disclosure

The DX Challenge was designed and coded with the assistance of generative artificial-intelligence tools. AI assistance has been used under human direction for activities such as planning, drafting code and documentation, debugging, reviewing, and testing. DX Central directs the project, reviews changes, makes operational and policy decisions, and remains responsible for the deployed App.

The deployed App does **not** currently contain a generative-AI feature, and it does not automatically send participant profiles, Google identity information, receiving locations, reception logs, bulk imports, support tickets, or shoutouts to an AI model. If a future feature would process participant information with an AI service, this Policy and the App will be updated to provide appropriate notice before or when that feature is introduced.

AI-assisted code, like human-written code, may contain errors. The App is tested and monitored, but participants should report unexpected behavior and independently verify important exported data or challenge results.

## 10. Third-party services and links

Google, Streamlit/Snowflake, GitHub, form providers, media hosts, and other linked sites operate under their own privacy policies and terms. DX Central does not control how those independent services process information. Opening a linked user guide, media file, station resource, or external form may take you to another service.

## 11. Children's privacy

The App is a general-audience amateur-radio hobby service and is not directed to children under 13. We do not knowingly solicit personal information from children under 13. A parent or guardian who believes a child has submitted personal information may contact DX Central through the in-App support process to request review or removal.

## 12. Changes to this Policy

We may update this Policy as the App, challenge rules, service providers, or legal requirements change. The effective date will be revised, and material changes will be identified in the Community page's Release notes or another prominent App notice.

## 13. Contact

For privacy questions or requests, open **Profile settings → Help & support**, choose the appropriate support category, and submit a ticket to the DX Central administrator.

## Service disclaimer

The DX Challenge is a hobby and community platform. Statistics, maps, station matches, awards, and challenge results depend on participant submissions, third-party station information, and automated calculations and may contain errors or omissions. Participation is voluntary. Each participant is responsible for the accuracy and lawfulness of the information and media they submit and for using receiving equipment in accordance with applicable rules. Features and availability may change, and the App is provided without a guarantee of uninterrupted or error-free operation.
