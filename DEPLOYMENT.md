# The DX Challenge · Season 7 staging deployment

1. Upload the contents of this package to the repository root on the `main` branch.
2. Keep Streamlit Community Cloud's entry point set to `app.py`.
3. Do not upload a real `.streamlit/secrets.toml` file. Keep credentials only in
   Streamlit's Secrets editor.
4. In the existing `[app]` secrets section, set `writes_enabled = true` when this
   build is ready to mirror staging records to the private Google Sheet.
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

The first launch of this release also creates or validates the **Challenges** tab and
adds the new review/support columns without dropping existing Sheet columns.
