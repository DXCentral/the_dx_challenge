from pathlib import Path

import pandas as pd
import streamlit as st

from app_support import (
    community_shoutout_config,
    community_shoutout_csv_url,
    load_community_shoutouts,
    load_published_community_shoutouts,
)
from dxcore.config import APP_VERSION, CONTENT_DIR
from dxcore.shoutouts import CATEGORY_PRESENTATION, observed_categories


def read_content(name: str, fallback: str) -> str:
    path = Path(CONTENT_DIR) / name
    return path.read_text(encoding="utf-8").strip() if path.exists() else fallback


def clear_shoutout_filters() -> None:
    st.session_state.shoutout_filter_version = int(
        st.session_state.get("shoutout_filter_version", 0)
    ) + 1


st.title("Community")
st.caption("Celebrate standout catches and DX milestones without exposing private account or station-list data.")

with st.container(horizontal=True, vertical_alignment="center"):
    st.badge(f"Version {APP_VERSION}", icon=":material/new_releases:", color="blue")
    st.caption("Season 7 staging build")

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

                filtered = shoutouts.copy()
                if dxer_filter != "All DXers":
                    filtered = filtered[filtered["name"] == dxer_filter]
                if category_filter != "All categories":
                    filtered = filtered[
                        filtered["categories"].map(lambda values: category_filter in values)
                    ]
                if month_filter != "All months":
                    filtered = filtered[filtered["submission_month"] == month_filter]
                filtered = filtered.reset_index(drop=True)

                st.caption(
                    f"Showing {len(filtered):,} of {len(shoutouts):,} shoutout(s), newest first."
                )
                if filtered.empty:
                    st.info("No shoutouts match the selected filters.")
                else:
                    page_size = 20
                    page_count = max(1, (len(filtered) + page_size - 1) // page_size)
                    page = (
                        st.selectbox(
                            "Page",
                            list(range(1, page_count + 1)),
                            key=f"shoutout_page_{version}",
                            width=120,
                        )
                        if page_count > 1
                        else 1
                    )
                    visible = filtered.iloc[(page - 1) * page_size : page * page_size]
                    for row in visible.to_dict("records"):
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
                            submitted = row.get("submitted_at")
                            if pd.notna(submitted):
                                st.caption(f"Submitted {pd.Timestamp(submitted):%B %d, %Y}")
                            with st.container(horizontal=True, gap="small"):
                                for category in row["categories"]:
                                    icon, color = CATEGORY_PRESENTATION.get(
                                        category, (":material/celebration:", "gray")
                                    )
                                    st.badge(category, icon=icon, color=color)
                            st.write(row["details"])
                            if str(row["upload_url"]).strip():
                                st.link_button(
                                    "Open attached media",
                                    str(row["upload_url"]).strip(),
                                    icon=":material/play_circle:",
                                )

with st.container(border=True):
    st.subheader("Livestream prompts")
    st.write("Announcements and community goals can support the weekly DX livestream without becoming a chat or social network.")

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
