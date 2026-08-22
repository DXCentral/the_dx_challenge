from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from dxcore.config import CONTENT_DIR, DEFAULT_USER_ID, DEFAULT_USER_NAME, STAGING_SPREADSHEET_ID
from dxcore.content import load_challenges
from dxcore.stations import frequencies_for_band, load_stations
from dxcore.store import LocalStore
from dxcore.themes import theme_css


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
    store = get_store()
    store.upsert_user(user["user_id"], user["email"], user["display_name"])
    profile = store.user_profile(user["user_id"]) or user
    st.session_state.user = {
        "user_id": user["user_id"],
        "email": user["email"],
        "display_name": str(profile.get("display_name", user["display_name"])),
        "theme_name": str(profile.get("theme_name", "Midnight blue")),
        "large_text": bool(profile.get("large_text", 0)),
        "reduce_motion": bool(profile.get("reduce_motion", 0)),
        "walkthrough_complete": bool(profile.get("walkthrough_complete", 0)),
    }
    st.session_state.setdefault("active_location_id", "")
    if "pending_active_location_id" in st.session_state:
        st.session_state.active_location_id = st.session_state.pop("pending_active_location_id")


def render_user_theme() -> None:
    user = st.session_state.get("user", {})
    st.html(
        theme_css(
            str(user.get("theme_name", "Midnight blue")),
            bool(user.get("large_text", False)),
            bool(user.get("reduce_motion", False)),
        )
    )


def display_names() -> dict[str, str]:
    users = get_store().users()
    if users.empty:
        return {}
    return dict(zip(users["user_id"].astype(str), users["display_name"].astype(str), strict=False))


def support_email() -> str:
    path = CONTENT_DIR / "support_email.txt"
    if not path.exists():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if value and not value.startswith("#") and "@" in value and value != "support@example.com":
            return value
    return ""


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
    instant = now or datetime.now(timezone.utc)
    challenges = load_challenges()
    current = [item for item in challenges if item["start_utc"] <= instant <= item["end_utc"]]
    previous = sorted(
        [item for item in challenges if item["end_utc"] < instant], key=lambda item: item["end_utc"], reverse=True
    )
    future = sorted([item for item in challenges if item["start_utc"] > instant], key=lambda item: item["start_utc"])
    return current, previous, future


@st.dialog("Welcome to The DX Challenge", width="large")
def walkthrough_dialog() -> None:
    steps = [
        ("Set up a receiving location", "Open Profile settings and add your Home QTH or a portable location. Every reception stays tied to the location you used."),
        ("Complete a bandscan", "Review every channel on MW, FM, or NWR. Log a heard station or mark the channel OPEN. Completing a band unlocks normal logging at that location."),
        ("Submit receptions", "Choose a band and frequency, select a station, review the timestamp and propagation details, then submit. Row selection alone never creates a log."),
        ("Track your season", "Use My logbook to edit, delete, or export only your own logs. Awards, challenges, leaderboards, and Stats use canonical unique-station calculations."),
        ("Get help", "Return to Profile settings at any time to restart this tour or prepare a support request."),
    ]
    step = int(st.session_state.get("walkthrough_step", 0))
    step = max(0, min(step, len(steps) - 1))
    title, body = steps[step]
    st.caption(f"Step {step + 1} of {len(steps)}")
    st.subheader(title)
    st.write(body)
    st.progress((step + 1) / len(steps))
    with st.container(horizontal=True, horizontal_alignment="distribute"):
        if st.button("Skip tour", icon=":material/close:"):
            get_store().update_user_preferences(
                st.session_state.user["user_id"], walkthrough_complete=True
            )
            st.session_state.user["walkthrough_complete"] = True
            st.session_state.pop("force_walkthrough", None)
            st.session_state.pop("walkthrough_step", None)
            st.rerun()
        if step > 0 and st.button("Previous", icon=":material/arrow_back:"):
            st.session_state.walkthrough_step = step - 1
            st.rerun()
        if step < len(steps) - 1:
            if st.button("Next", icon=":material/arrow_forward:", type="primary"):
                st.session_state.walkthrough_step = step + 1
                st.rerun()
        elif st.button("Finish", icon=":material/check_circle:", type="primary"):
            get_store().update_user_preferences(
                st.session_state.user["user_id"], walkthrough_complete=True
            )
            st.session_state.user["walkthrough_complete"] = True
            st.session_state.pop("force_walkthrough", None)
            st.session_state.pop("walkthrough_step", None)
            st.rerun()


def maybe_show_walkthrough() -> None:
    if st.session_state.get("force_walkthrough") or not st.session_state.user.get(
        "walkthrough_complete", False
    ):
        walkthrough_dialog()
