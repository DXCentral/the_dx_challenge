from urllib.parse import quote

import streamlit as st
from geopy.geocoders import Nominatim

from app_support import (
    authentication_configured,
    get_store,
    operating_locations,
    support_email,
)
from dxcore.geo import grid_to_latlon, haversine_miles, latlon_to_grid
from dxcore.themes import THEMES


st.title("Profile settings")
st.caption("Manage your DXer identity, display preferences, accessibility options, receiving locations, and help tools.")

user = st.session_state.user
store = get_store()
locations = operating_locations()

if st.session_state.pop("profile_location_saved", False):
    st.toast("Location saved. Future receptions can now be tied to this QTH.")
if notice := st.session_state.pop("profile_notice", None):
    st.toast(notice)

with st.container(border=True):
    st.subheader("DXer profile")
    with st.form("display_name_form", border=False):
        display_name = st.text_input(
            "Display name",
            value=str(user["display_name"]),
            max_chars=80,
        help="This name appears in leaderboards, awards, challenges, and community views. It does not change your Google account.",
        )
        st.caption(user["email"])
        save_name = st.form_submit_button(
            "Save display name", icon=":material/badge:", type="primary"
        )
    if save_name:
        try:
            store.update_user_preferences(user["user_id"], display_name=display_name)
            st.session_state.user["display_name"] = display_name.strip()
            st.session_state.profile_notice = (
                "Display name updated for this account and all of its historical results."
            )
            st.rerun()
        except ValueError as error:
            st.error(str(error))
    st.badge(
        "Google-authenticated account" if authentication_configured() else "Local test identity",
        icon=":material/verified_user:" if authentication_configured() else ":material/science:",
        color="blue",
    )
    st.caption(
        "Reception ownership uses your stable signed-in account ID, not a copied name. "
        "Changing this value therefore updates historical leaderboards and awards without creating a second DXer."
    )

with st.container(border=True):
    st.subheader("Display and accessibility")
    theme_names = list(THEMES)
    current_theme = str(user.get("theme_name", "Midnight blue"))
    if current_theme not in theme_names:
        current_theme = "Midnight blue"
    with st.form("display_preferences_form", border=False):
        theme_name = st.selectbox(
            "Color palette",
            theme_names,
            index=theme_names.index(current_theme),
            help="High contrast uses white text, black surfaces, and a bright cyan focus indicator.",
        )
        large_text = st.toggle(
            "Larger interface text",
            value=bool(user.get("large_text", False)),
            help="Increases the base text size while keeping charts and tables responsive.",
        )
        reduce_motion = st.toggle(
            "Reduce animation and motion",
            value=bool(user.get("reduce_motion", False)),
        )
        save_display = st.form_submit_button(
            "Apply display settings", icon=":material/palette:", type="primary"
        )
    if save_display:
        store.update_user_preferences(
            user["user_id"],
            theme_name=theme_name,
            large_text=large_text,
            reduce_motion=reduce_motion,
        )
        st.session_state.user.update(
            {"theme_name": theme_name, "large_text": large_text, "reduce_motion": reduce_motion}
        )
        st.session_state.profile_notice = f"{theme_name} display settings applied."
        st.rerun()
    st.caption(
        "Theme control lives here rather than following the browser or operating-system setting. Every palette keeps text status alongside color; High contrast is designed for maximum separation."
    )


@st.dialog("Add a receiving location", width="large")
def add_location_dialog() -> None:
    method = st.segmented_control(
        "Lookup method",
        ["City / region", "Maidenhead grid", "Manual coordinates"],
        default="City / region",
        key="profile_location_method",
    )
    with st.form("add_location_form"):
        label = st.text_input("Location label", placeholder="Home, Beach portable, Cabin…")
        city = st.text_input("City")
        region = st.text_input("State / province / region")
        country = st.text_input("Country", value="United States")
        grid = ""
        latitude = 0.0
        longitude = 0.0
        if method == "Maidenhead grid":
            grid = st.text_input("4- or 6-character grid", placeholder="EM40 or EM40AE").upper()
        elif method == "Manual coordinates":
            latitude = st.number_input(
                "Latitude", min_value=-90.0, max_value=90.0, value=0.0, format="%.6f"
            )
            longitude = st.number_input(
                "Longitude", min_value=-180.0, max_value=180.0, value=0.0, format="%.6f"
            )
        make_home = st.checkbox("Make this my Home QTH", value=locations.empty)
        submitted = st.form_submit_button(
            "Save location", icon=":material/save:", type="primary"
        )

    if submitted:
        try:
            if not label.strip():
                label = city.strip() or grid.strip() or "New QTH"
            if method == "Maidenhead grid":
                latitude, longitude = grid_to_latlon(grid)
            elif method == "City / region":
                query = ", ".join(
                    value for value in [city.strip(), region.strip(), country.strip()] if value
                )
                if not query:
                    raise ValueError("Enter a city, region, or country to search.")
                result = Nominatim(user_agent="dx_challenge_s7_staging", timeout=8).geocode(query)
                if result is None:
                    raise ValueError(
                        "That location could not be found. Try a grid or manual coordinates."
                    )
                latitude, longitude = float(result.latitude), float(result.longitude)
            if not grid:
                grid = latlon_to_grid(latitude, longitude)
            location_id = store.add_location(
                user["user_id"],
                {
                    "label": label.strip(),
                    "city": city.strip(),
                    "region": region.strip(),
                    "country": country.strip(),
                    "grid": grid,
                    "latitude": latitude,
                    "longitude": longitude,
                    "is_home": make_home,
                },
            )
            st.session_state.pending_active_location_id = location_id
            st.session_state.profile_location_saved = True
            st.rerun()
        except (ValueError, OSError) as error:
            st.error(str(error))


st.subheader("Receiving locations")
if st.button("Add a receiving location", icon=":material/add_location_alt:"):
    add_location_dialog()

locations = operating_locations()
if locations.empty:
    st.info("No locations saved yet.")
else:
    display = locations[
        ["label", "city", "region", "country", "grid", "latitude", "longitude", "is_home"]
    ].copy()
    display["is_home"] = display["is_home"].map({1: "Home", 0: "Portable / alternate"})
    st.dataframe(display, hide_index=True)

    location_records = locations.to_dict("records")
    choices = {
        row["location_id"]: (
            f"{row['label']} · {row['city']}, {row['region']} · "
            f"{'Home' if int(row['is_home']) else 'Alternate'}"
        )
        for row in location_records
    }
    new_home = st.selectbox("Set Home QTH", options=list(choices), format_func=choices.get)
    current_home = locations[locations["is_home"] == 1]
    if not current_home.empty:
        selected_row = locations[locations["location_id"] == new_home].iloc[0]
        home_row = current_home.iloc[0]
        movement = haversine_miles(
            home_row["latitude"],
            home_row["longitude"],
            selected_row["latitude"],
            selected_row["longitude"],
        )
        st.caption(
            f"Distance from current Home QTH: {movement:,.1f} miles. Existing locations and their reception history remain available after the change."
        )
    if st.button("Update Home QTH", icon=":material/home_pin:"):
        store.set_home_location(user["user_id"], new_home)
        st.session_state.pending_active_location_id = new_home
        st.session_state.profile_notice = (
            "Home QTH updated. Previous locations and their logs remain available."
        )
        st.rerun()

    st.markdown("**Delete an unused location**")
    delete_choice = st.selectbox(
        "Location to delete",
        options=list(choices),
        format_func=choices.get,
        key="profile_delete_location",
    )
    usage = store.location_usage(user["user_id"], delete_choice)
    if usage["logs"]:
        st.warning(
            f"Locked: this location is tied to {usage['logs']:,} active log(s)."
        )
    else:
        st.caption("Only unused locations can be deleted. This action cannot be undone.")
        if st.button("Delete selected location", icon=":material/delete:"):
            deleted, message = store.delete_location(user["user_id"], delete_choice)
            if deleted:
                if st.session_state.get("active_location_id") == delete_choice:
                    st.session_state.pending_active_location_id = ""
                st.session_state.profile_notice = message
                st.rerun()
            st.error(message)

with st.container(border=True):
    st.subheader("Help and support")
    if st.button("Start guided walkthrough", icon=":material/tour:"):
        st.session_state.force_walkthrough = True
        st.session_state.walkthrough_step = 0
        st.rerun()

    inbox = support_email()
    with st.form("support_ticket_form"):
        category = st.selectbox(
            "Support category",
            [
                "Logging entry", "Bandscan", "Import", "Award or leaderboard",
                "Location", "Feature request", "Other",
            ],
        )
        subject = st.text_input("Subject", max_chars=120)
        details = st.text_area(
            "What happened?",
            placeholder="Include the page, station/frequency, approximate UTC time, and what you expected to happen.",
        )
        prepare_ticket = st.form_submit_button(
            "Prepare support ticket", icon=":material/support_agent:", type="primary"
        )
    if prepare_ticket:
        if not subject.strip() or not details.strip():
            st.error("Enter both a subject and details.")
        else:
            ticket_id = store.create_support_ticket(
                user["user_id"], category, subject.strip(), details.strip()
            )
            body = (
                f"Ticket: {ticket_id}\n"
                f"DXer: {user['display_name']}\n"
                f"Account: {user['email']}\n"
                f"Category: {category}\n\n"
                f"{details.strip()}"
            )
            st.session_state.support_mailto = (
                f"mailto:{inbox}?subject={quote('[DX Challenge] ' + subject.strip())}&body={quote(body)}"
                if inbox
                else ""
            )
            st.session_state.support_ticket_id = ticket_id
            st.session_state.profile_notice = (
                f"Support ticket {ticket_id} was submitted to the administrator portal."
            )
            st.rerun()
    if ticket_id := st.session_state.get("support_ticket_id"):
        st.success(
            f"Support ticket {ticket_id} is recorded."
        )
        if mailto := st.session_state.get("support_mailto"):
            st.link_button("Also open email app", mailto, icon=":material/mail:")

    tickets = store.support_tickets(user["user_id"])
    open_tickets = tickets[~tickets["status"].isin(["Resolved", "Closed"])] if not tickets.empty else tickets
    st.markdown("**Your open tickets**")
    if open_tickets.empty:
        st.caption("No open support or feature-request tickets.")
    else:
        st.dataframe(
            open_tickets[
                ["ticket_id", "category", "subject", "created_utc", "updated_utc", "status", "admin_comment"]
            ].rename(columns={"admin_comment": "Most recent administrator comment"}),
            hide_index=True,
            column_config={
                "ticket_id": st.column_config.TextColumn("Ticket"),
                "created_utc": st.column_config.DatetimeColumn("Created", format="YYYY-MM-DD HH:mm"),
                "updated_utc": st.column_config.DatetimeColumn("Updated", format="YYYY-MM-DD HH:mm"),
            },
        )

st.caption(
    "Data tables cannot be downloaded except through the protected export in My logbook."
)
