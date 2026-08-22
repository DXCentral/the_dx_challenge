# The DX Challenge · Season 7 staging deployment

1. Upload the contents of this package to the repository root on the `main` branch.
2. Keep Streamlit Community Cloud's entry point set to `app.py`.
3. Do not upload a real `.streamlit/secrets.toml` file. Keep credentials only in
   Streamlit's Secrets editor.
4. In the existing `[app]` secrets section, set `writes_enabled = true` when this
   build is ready to mirror staging records to the private Google Sheet.
5. Reboot the app after the deploy so the new Python modules and dependencies are
   loaded together.

On the first authenticated launch with valid service-account credentials, the app
creates or validates its managed Google Sheet tabs and hydrates the fast local cache.
The app bar should say **durable sync active**. If it shows the cloud-off warning,
inspect the private Streamlit logs before inviting testers; the app will not display
credential details in the public UI.

Routine season content can be edited without Python changes:

- `content/announcements.csv`
- `content/challenge_schedule.csv`
- `content/release_notes.md`
- `content/privacy_policy.md`
- `content/support_email.txt`
