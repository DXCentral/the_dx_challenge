from pathlib import Path
import pandas as pd
import streamlit as st

from app_support import (
    admin_session_authorized,
    app_environment,
    community_shoutout_config,
    community_shoutout_csv_url,
    display_names,
    get_store,
    load_community_shoutouts,
    load_published_community_shoutouts,
    season_eligible_logs,
)
from dxcore.awards import award_milestones
from dxcore.config import APP_VERSION, CONTENT_DIR
from dxcore.shoutouts import CATEGORY_PRESENTATION, media_filename, observed_categories


def read_content(name: str, fallback: str) -> str:
    path = Path(CONTENT_DIR) / name
    return path.read_text(encoding="utf-8").strip() if path.exists() else fallback


def clear_shoutout_filters() -> None:
    st.session_state.shoutout_filter_version = int(
        st.session_state.get("shoutout_filter_version", 0)
    ) + 1
    st.session_state.pop("shoutout_carousel_signature", None)
    st.session_state.pop("shoutout_carousel_index", None)


def move_shoutout(amount: int, total: int) -> None:
    if total <= 0:
        return
    current = int(st.session_state.get("shoutout_carousel_index", 0))
    st.session_state.shoutout_carousel_index = (current + amount) % total


def stored_boolean(value: object) -> bool:
    return str(value).strip().casefold() in {"1", "true", "yes", "on"}


def update_shoutout_read(entry_id: str, widget_key: str) -> None:
    if not admin_session_authorized():
        st.session_state.shoutout_status_notice = (
            "Administrator authorization expired. Open Admin and sign in again."
        )
        return
    updated, message = get_store().set_shoutout_read(
        entry_id, bool(st.session_state.get(widget_key, False))
    )
    st.session_state.shoutout_status_notice = message
    if not updated:
        st.session_state[widget_key] = not bool(st.session_state.get(widget_key, False))


st.title("Community")
st.caption("Celebrate standout catches and DX milestones without exposing private account or station-list data.")

with st.container(horizontal=True, vertical_alignment="center"):
    st.badge(f"Version {APP_VERSION}", icon=":material/new_releases:", color="blue")
    st.caption(f"Season 7 {app_environment().title()} build")

with st.container(border=True):
    st.subheader("DXer shoutouts")
    st.write(
        "A virtual high five for new logs, new places, milestones, gear, and other catches shared with the DX Central livestream."
    )
    csv_url = community_shoutout_csv_url()
    spreadsheet_id, worksheet_name = community_shoutout_config()
    if not csv_url and not spreadsheet_id:
        st.info(
            "The shoutout feed is ready but has not been connected to its Google Sheet yet.",
            icon=":material/add_link:",
        )
    else:
        try:
            with st.spinner("Loading shoutouts…"):
                shoutouts = (
                    load_published_community_shoutouts(csv_url)
                    if csv_url
                    else load_community_shoutouts(spreadsheet_id, worksheet_name)
                )
        except Exception:
            st.warning(
                "The shoutout Sheet could not be read. The administrator can verify the Sheet ID, tab name, and service-account sharing.",
                icon=":material/cloud_off:",
            )
        else:
            if csv_url:
                st.caption("Published shoutouts refresh automatically about every five minutes.")
            if shoutouts.empty:
                st.caption("No shoutouts have been submitted yet.")
            else:
                status_rows = get_store().shoutout_statuses()
                status_lookup = (
                    status_rows.set_index("entry_id")["read_on_air"].to_dict()
                    if not status_rows.empty
                    else {}
                )
                version = int(st.session_state.get("shoutout_filter_version", 0))
                names = sorted(shoutouts["name"].dropna().astype(str).unique(), key=str.casefold)
                categories = observed_categories(shoutouts)
                months = sorted(shoutouts["submission_month"].dropna().unique(), reverse=True)
                filter_columns = st.columns(3)
                dxer_filter = filter_columns[0].selectbox(
                    "DXer",
                    ["All DXers", *names],
                    key=f"shoutout_dxer_{version}",
                )
                category_filter = filter_columns[1].selectbox(
                    "Category",
                    ["All categories", *categories],
                    key=f"shoutout_category_{version}",
                )
                if months:
                    month_filter = filter_columns[2].selectbox(
                        "Submission month",
                        ["All months", *months],
                        format_func=lambda value: (
                            value if isinstance(value, str) else value.strftime("%B %Y")
                        ),
                        key=f"shoutout_month_{version}",
                    )
                else:
                    month_filter = "All months"
                    filter_columns[2].text_input(
                        "Submission month",
                        value="Unavailable — add a Timestamp column",
                        disabled=True,
                        key=f"shoutout_month_unavailable_{version}",
                    )
                st.button(
                    "Clear filters",
                    icon=":material/filter_alt_off:",
                    on_click=clear_shoutout_filters,
                    key=f"clear_shoutout_filters_{version}",
                )
                air_status_filter = "All shoutouts"
                if admin_session_authorized():
                    air_status_filter = st.selectbox(
                        "Livestream status (administrator)",
                        ["All shoutouts", "Not yet read", "Read on air"],
                        key=f"shoutout_air_status_{version}",
                    )

                filtered = shoutouts.copy()
                if dxer_filter != "All DXers":
                    filtered = filtered[filtered["name"] == dxer_filter]
                if category_filter != "All categories":
                    filtered = filtered[
                        filtered["categories"].map(lambda values: category_filter in values)
                    ]
                if month_filter != "All months":
                    filtered = filtered[filtered["submission_month"] == month_filter]
                if air_status_filter != "All shoutouts":
                    is_read = filtered["entry_id"].astype(str).map(
                        lambda value: stored_boolean(status_lookup.get(value, False))
                    )
                    filtered = filtered[
                        is_read if air_status_filter == "Read on air" else ~is_read
                    ]
                filtered = filtered.reset_index(drop=True)

                st.caption(
                    f"Showing {len(filtered):,} of {len(shoutouts):,} shoutout(s), newest first."
                )
                if filtered.empty:
                    st.info("No shoutouts match the selected filters.")
                else:
                    signature = "|".join(filtered["entry_id"].astype(str))
                    if st.session_state.get("shoutout_carousel_signature") != signature:
                        st.session_state.shoutout_carousel_signature = signature
                        st.session_state.shoutout_carousel_index = 0
                    index = int(st.session_state.get("shoutout_carousel_index", 0)) % len(filtered)
                    st.session_state.shoutout_carousel_index = index
                    previous, position, following = st.columns(
                        [1, 4, 1], vertical_alignment="center"
                    )
                    previous.button(
                        "Previous shoutout",
                        icon=":material/arrow_back:",
                        on_click=move_shoutout,
                        args=(-1, len(filtered)),
                        disabled=len(filtered) <= 1,
                        key=f"shoutout_previous_{version}",
                    )
                    with position.container(horizontal_alignment="center"):
                        st.caption(f"Shoutout {index + 1:,} of {len(filtered):,}")
                    following.button(
                        "Next shoutout",
                        icon=":material/arrow_forward:",
                        on_click=move_shoutout,
                        args=(1, len(filtered)),
                        disabled=len(filtered) <= 1,
                        key=f"shoutout_next_{version}",
                    )

                    row = filtered.iloc[index].to_dict()
                    entry_id = str(row["entry_id"]).strip()
                    read_on_air = stored_boolean(status_lookup.get(entry_id, False))
                    with st.container(border=True):
                        location = ", ".join(
                            value
                            for value in (
                                str(row["region"]).strip(),
                                str(row["country"]).strip(),
                            )
                            if value
                        )
                        st.markdown(
                            f"**{row['name']}**" + (f" · {location}" if location else "")
                        )
                        if read_on_air:
                            st.badge(
                                "Read on air",
                                icon=":material/campaign:",
                                color="green",
                            )
                        submitted = row.get("submitted_at")
                        if pd.notna(submitted):
                            st.caption(
                                f"Submitted {pd.Timestamp(submitted):%B %d, %Y} UTC"
                            )
                        with st.container(horizontal=True, gap="small"):
                            for category in row["categories"]:
                                icon, color = CATEGORY_PRESENTATION.get(
                                    category, (":material/celebration:", "gray")
                                )
                                st.badge(category, icon=icon, color=color)
                        st.write(row["details"])
                        if str(row["upload_url"]).strip():
                            with st.container(horizontal=True, vertical_alignment="center"):
                                st.link_button(
                                    "Open attached media",
                                    str(row["upload_url"]).strip(),
                                    icon=":material/play_circle:",
                                )
                                st.caption(f"File: {media_filename(row['upload_url'])}")
                        if admin_session_authorized():
                            widget_key = f"admin_shoutout_read_{entry_id}"
                            if widget_key not in st.session_state:
                                st.session_state[widget_key] = read_on_air
                            st.checkbox(
                                "Marked as read on the livestream",
                                key=widget_key,
                                on_change=update_shoutout_read,
                                args=(entry_id, widget_key),
                                help=(
                                    "Administrator-only control. The public read-on-air badge "
                                    "updates for every viewer."
                                ),
                            )

                if notice := st.session_state.pop("shoutout_status_notice", None):
                    st.toast(notice)

with st.container(border=True):
    st.subheader("Achievement Corner")
    st.write("The latest Season 7 award qualifications and endorsement milestones across DXers.")
    milestones = award_milestones(
        season_eligible_logs(get_store().logs()), display_names()
    ).head(8)
    if milestones.empty:
        st.caption("No Season 7 award milestones have been earned yet.")
    else:
        for milestone in milestones.to_dict("records"):
            with st.container(border=True):
                st.markdown(
                    f":material/trophy: **{milestone['dxer']}** earned "
                    f"**{milestone['milestone']}**"
                )
                st.caption(
                    f"{pd.Timestamp(milestone['achieved_utc']):%B %d, %Y} UTC · "
                    f"{milestone['summary']}"
                )

with st.container(border=True):
    st.subheader("Release notes")
    st.markdown(
        read_content(
            "release_notes.md",
            "Release notes will be published here as testing builds are promoted.",
        )
    )

with st.container(border=True):
    st.subheader("Privacy policy and disclaimer")
    st.markdown(
        read_content(
            "privacy_policy.md",
            "The privacy policy is being prepared for the public Season 7 launch.",
        )
    )
