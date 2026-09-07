# The DX Challenge · Season 7 deployment

1. Upload the contents of this package to the repository root on the `main` branch.
2. Keep Streamlit Community Cloud's entry point set to `app.py`.
3. Do not upload a real `.streamlit/secrets.toml` file. Keep credentials only in
   Streamlit's Secrets editor.
4. In the existing `[app]` secrets section, identify the environment and its own
   private Google Sheet. The same code can therefore power an isolated staging app
   and a clean production app:

   ```toml
   [app]
   environment = "staging"
   spreadsheet_id = "YOUR_STAGING_SHEET_ID"
   writes_enabled = true
   ```

   Use `environment = "production"` and a different, blank private Sheet ID in the
   production app's Secrets. Never point both deployments at the same Sheet.
5. Add an `[admin]` section to Streamlit Secrets. Its `email` must exactly match the
   Google account that should see the Admin page. Use a long, unique second password:

   ```toml
   [admin]
   email = "your-admin-google-address@example.com"
   password = "REPLACE_WITH_A_LONG_UNIQUE_ADMIN_PASSWORD"
   ```

   Never commit the real password or paste it into a support message.
6. Reboot the app after the deploy so the new Python modules and dependencies are
   loaded together.

Each Streamlit deployment must also have its own exact OAuth callback in `[auth]`.
For example:

```toml
# Production app Secrets
[auth]
redirect_uri = "https://thedxchallenge.streamlit.app/oauth2callback"

# Staging app Secrets (in the separate staging app, not in the same TOML file)
[auth]
redirect_uri = "https://thedxchallenge-stage.streamlit.app/oauth2callback"
```

Add both exact values to the Google OAuth client's **Authorized redirect URIs**.
Do not use the production callback in staging, and do not add a trailing slash after
`oauth2callback`.

**Community → DXer shoutouts** reads the published CSV URL in
`content/shoutouts_source.txt`; no additional Streamlit secret or service-account
permission is required. Replace that one-line URL if the published feed ever moves.

As an optional private-Sheet fallback, clear `content/shoutouts_source.txt`, share the
response Sheet with the existing service-account email as **Viewer**, and add:

```toml
[community]
shoutouts_spreadsheet_id = "YOUR_SHOUTOUT_SPREADSHEET_ID"
shoutouts_worksheet = "Sheet1"
```

The feed reads only the public name, region, country, category, details, aircheck,
and submission-date fields. It refreshes in the background about every five minutes.

On the first authenticated launch with valid service-account credentials, the app
creates or validates its managed Google Sheet tabs and hydrates the fast local cache.
The app bar should say **durable sync active**. If it shows the cloud-off warning,
inspect the private Streamlit logs before inviting testers; the app will not display
credential details in the public UI.

Routine deployed content is now managed from the protected **Admin** page:

- Announcements, including optional start/end windows
- Active, future, or draft challenges and their qualifying/scoring criteria
- Support and feature-request status plus the latest administrator response
- Unlisted stations submitted through manual entry or importer review

`content/announcements.csv` and `content/challenge_schedule.csv` remain installation
seeds. Release notes, privacy text, and the support email remain repository-managed
Markdown/text files.

The first launch of this release also creates or validates **Challenges**, **Import
Review**, and the other managed tabs without dropping existing Sheet columns. Import
Review holds a DXer's unresolved upload rows so they can finish later from My Logbook.
The private **Shoutout Status** tab is used only for the administrator's durable
read-on-air flags; the published WPForms response feed remains read-only.

## Keep staging and production isolated

| Environment | App URL | Google Sheet ID |
|---|---|---|
| Staging | `https://thedxchallenge-stage.streamlit.app/` | `1Z0C_bnxCgVMWdhP26MbvKqsGCNcCab0zeSQiIpJzn2A` |
| Production | `https://thedxchallenge.streamlit.app/` | `1EMPxrbrNZlrq2BzbqdBNeW8ZFVTR325Q_hztMJ7hAO8` |

1. Preserve the current beta Google Sheet as the staging data store; do not delete its logs.
2. Create a `staging` branch in GitHub and deploy it as a second Streamlit app, for
   `thedxchallenge-stage.streamlit.app`.
3. Copy the existing staging secrets to that app, keeping the current staging Sheet ID
   and changing `auth.redirect_uri` to the staging app's `/oauth2callback` URL.
4. Add that redirect URI in the Google OAuth client alongside the production URI.
5. Keep `main` as production. Make a separate restricted **production copy** of the
   staging Sheet and share that copy with the service account as Editor. In the copy
   only, preserve the header row but clear the data rows from **Users**, **Locations**,
   **Logging Entries**, **Bandscan**, **Import Batches**, **Import Review**, **Support
   Tickets**, and **Shoutout Status**. Keep **Challenges**, **Announcements**, and
   reviewed **Station Overrides** so production retains the approved operating
   configuration. Put only this copied Sheet's ID in production Secrets.
6. Reboot both apps and confirm their app bars say **Staging** and **Production** and
   show different final eight characters for their private Sheet IDs.

This preserves all beta data for demonstrations and feature testing while production
starts with empty managed tabs. In production, the Google Sheet is authoritative at
startup—even when a managed tab is intentionally empty—so a cleared production Sheet
also clears any stale rows in the fast local cache. Staging keeps its safer tab-seeding
behavior for upgrades. The cache is additionally isolated by environment and Sheet ID.
Do not "clear" production by deleting staging rows.
