from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from dxcore.config import DEFAULT_USER_ID, DEFAULT_USER_NAME, STAGING_SPREADSHEET_ID
from dxcore.stations import frequencies_for_band, load_stations
from dxcore.store import LocalStore


@st.cache_resource
def get_store() -> LocalStore:
    return LocalStore()


@st.cache_data
def get_station_data() -> pd.DataFrame:
    return load_stations()


def authentication_configured() -> bool:
    try:
        return "auth" in st.secrets
    except (FileNotFoundError, KeyError):
        return False


def sheets_credentials_configured() -> bool:
    try:
        return "gcp_service_account" in st.secrets
    except (FileNotFoundError, KeyError):
        return False


def require_authentication() -> None:
    """Require Google login in deployed/secret-backed environments only."""
    if not authentication_configured() or st.user.is_logged_in:
        return
    st.title("The DX Challenge")
    with st.container(border=True, width=520):
        st.subheader("Sign in to continue")
        st.write(
            "Use the Google account associated with your DX Challenge profile. "
            "Your reception logs and receiving locations are tied to this identity."
        )
        st.button(
            "Sign in with Google",
            icon=":material/login:",
            type="primary",
            on_click=st.login,
        )
    st.caption("The first-time setup walkthrough appears after authentication and can be skipped.")
    st.stop()


def current_user() -> dict[str, str]:
    if authentication_configured() and st.user.is_logged_in:
        email = str(st.user.get("email", "")).strip().lower()
        subject = str(st.user.get("sub", email)).strip()
        name = str(st.user.get("name", email or "DXer")).strip()
        return {"user_id": subject, "email": email, "display_name": name}
    return {"user_id": DEFAULT_USER_ID, "email": DEFAULT_USER_ID, "display_name": DEFAULT_USER_NAME}


def initialize_app_state() -> None:
    user = current_user()
    get_store().upsert_user(user["user_id"], user["email"], user["display_name"])
    st.session_state.setdefault("user", user)
    st.session_state.setdefault("active_location_id", "")
    if "pending_active_location_id" in st.session_state:
        st.session_state.active_location_id = st.session_state.pop("pending_active_location_id")


def operating_locations() -> pd.DataFrame:
    return get_store().locations(st.session_state.user["user_id"])


def current_location() -> dict[str, object] | None:
    locations = operating_locations()
    if locations.empty:
        return None
    valid_ids = locations["location_id"].tolist()
    selected = st.session_state.get("active_location_id", "")
    if selected not in valid_ids:
        home = locations[locations["is_home"] == 1]
        selected = str((home.iloc[0] if not home.empty else locations.iloc[0])["location_id"])
        st.session_state.active_location_id = selected
    return locations[locations["location_id"] == selected].iloc[0].to_dict()


def render_app_bar() -> None:
    locations = operating_locations()
    with st.container(horizontal=True, vertical_alignment="center"):
        st.markdown("**The DX Challenge · Season 7**")
        if authentication_configured():
            st.badge(
                st.session_state.user["display_name"],
                icon=":material/account_circle:",
                color="blue",
            )
            st.button("Log out", icon=":material/logout:", on_click=st.logout)
        else:
            st.badge("Local test mode", icon=":material/science:", color="blue")
        if not locations.empty:
            records = locations.to_dict("records")
            labels = {
                row["location_id"]: f"{row['label']} · {row['city']}, {row['region']} ({row['grid']})"
                for row in records
            }
            st.selectbox(
                "Operating QTH",
                options=list(labels),
                format_func=labels.get,
                key="active_location_id",
                persist_state="session",
                width=360,
            )
        else:
            st.badge("Location required", icon=":material/location_off:", color="orange")
    st.caption(
        f"Google Sheet {STAGING_SPREADSHEET_ID[-8:]} is registered, but all writes remain local until private credentials pass validation."
    )


def require_location() -> dict[str, object]:
    location = current_location()
    if location is None:
        st.warning(
            "Create a receiving location in Profile Settings before using this page.",
            icon=":material/location_on:",
        )
        st.stop()
    return location


def bandscan_progress(location_id: str, band: str, mw_spacing: str = "10 kHz") -> tuple[int, int, float]:
    frequencies = frequencies_for_band(band, mw_spacing)
    scan = get_store().bandscan(st.session_state.user["user_id"], location_id, band)
    target = {round(value, 3) for value in frequencies}
    completed = (
        len({round(value, 3) for value in scan["frequency"].astype(float) if round(value, 3) in target})
        if not scan.empty
        else 0
    )
    total = len(frequencies)
    return completed, total, completed / total if total else 0.0


def challenge_status(now: datetime | None = None) -> tuple[list[dict], list[dict], list[dict]]:
    from challenge_rules import CHALLENGES

    instant = now or datetime.now(timezone.utc)
    current = [item for item in CHALLENGES if item["start_utc"] <= instant <= item["end_utc"]]
    previous = sorted(
        [item for item in CHALLENGES if item["end_utc"] < instant], key=lambda item: item["end_utc"], reverse=True
    )
    future = sorted([item for item in CHALLENGES if item["start_utc"] > instant], key=lambda item: item["start_utc"])
    return current, previous, future
