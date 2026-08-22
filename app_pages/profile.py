import streamlit as st
from geopy.geocoders import Nominatim

from app_support import current_location, get_store, operating_locations
from dxcore.geo import grid_to_latlon, haversine_miles, latlon_to_grid


st.title("Profile settings")
st.caption("Manage receiving locations, choose your Home QTH, and use the app menu to switch light/dark mode.")

user = st.session_state.user
store = get_store()
locations = operating_locations()

if st.session_state.pop("profile_location_saved", False):
    st.toast("Location saved. Its bandscans begin empty and logs remain tied to this QTH.")

with st.container(border=True):
    st.subheader("DXer profile")
    st.markdown(f"**{user['display_name']}**")
    st.caption(user["email"])
    st.badge("Development identity", icon=":material/science:", color="blue")

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
            latitude = st.number_input("Latitude", min_value=-90.0, max_value=90.0, value=0.0, format="%.6f")
            longitude = st.number_input("Longitude", min_value=-180.0, max_value=180.0, value=0.0, format="%.6f")
        make_home = st.checkbox("Make this my Home QTH", value=locations.empty)
        submitted = st.form_submit_button("Save location", icon=":material/save:", type="primary")

    if submitted:
        try:
            if not label.strip():
                label = city.strip() or grid.strip() or "New QTH"
            if method == "Maidenhead grid":
                latitude, longitude = grid_to_latlon(grid)
            elif method == "City / region":
                query = ", ".join(value for value in [city.strip(), region.strip(), country.strip()] if value)
                if not query:
                    raise ValueError("Enter a city, region, or country to search.")
                result = Nominatim(user_agent="dx_challenge_s7_staging", timeout=8).geocode(query)
                if result is None:
                    raise ValueError("That location could not be found. Try a grid or manual coordinates.")
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


if st.button("Add a receiving location", icon=":material/add_location_alt:"):
    add_location_dialog()

st.subheader("Saved locations")
locations = operating_locations()
if locations.empty:
    st.info("No locations saved yet.")
else:
    display = locations[["label", "city", "region", "country", "grid", "latitude", "longitude", "is_home"]].copy()
    display["is_home"] = display["is_home"].map({1: "Home", 0: "Portable / alternate"})
    st.dataframe(display, hide_index=True)

    location_records = locations.to_dict("records")
    choices = {row["location_id"]: f"{row['label']} · {row['city']}, {row['region']}" for row in location_records}
    new_home = st.selectbox("Set Home QTH", options=list(choices), format_func=choices.get)
    current_home = locations[locations["is_home"] == 1]
    if not current_home.empty:
        selected_row = locations[locations["location_id"] == new_home].iloc[0]
        home_row = current_home.iloc[0]
        movement = haversine_miles(
            home_row["latitude"], home_row["longitude"], selected_row["latitude"], selected_row["longitude"]
        )
        st.caption(
            f"Distance from current Home QTH: {movement:,.1f} miles. A location more than 25 miles away has its own bandscan requirements."
        )
    if st.button("Update Home QTH", icon=":material/home_pin:"):
        store.set_home_location(user["user_id"], new_home)
        st.session_state.pending_active_location_id = new_home
        st.success("Home QTH updated. Previous locations and their logs remain available.")
        st.rerun()

    st.divider()
    st.markdown("**Delete an unused location**")
    delete_choice = st.selectbox(
        "Location to delete",
        options=list(choices),
        format_func=choices.get,
        key="profile_delete_location",
    )
    usage = store.location_usage(user["user_id"], delete_choice)
    if usage["logs"] or usage["bandscan"]:
        st.warning(
            f"Locked: this location is tied to {usage['logs']:,} active log(s) and "
            f"{usage['bandscan']:,} bandscan result(s)."
        )
    else:
        st.caption("Only unused locations can be deleted. This action cannot be undone.")
        if st.button("Delete selected location", icon=":material/delete:"):
            deleted, message = store.delete_location(user["user_id"], delete_choice)
            if deleted:
                if st.session_state.get("active_location_id") == delete_choice:
                    st.session_state.pending_active_location_id = ""
                st.success(message)
                st.rerun()
            else:
                st.error(message)

with st.container(border=True):
    st.subheader("Display and accessibility")
    st.write(f"Current palette: **{st.context.theme.type.title()}**")
    st.write("Use the app menu in the upper-right → Theme to switch between the dark and daylight palettes.")
    st.markdown(
        "Keyboard navigation, visible labels, and text status alongside color are enabled throughout the staging build. "
        "Data tables cannot be downloaded except through the protected export in My logbook."
    )
