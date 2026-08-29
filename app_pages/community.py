from pathlib import Path

import streamlit as st

from dxcore.config import APP_VERSION, CONTENT_DIR


def read_content(name: str, fallback: str) -> str:
    path = Path(CONTENT_DIR) / name
    return path.read_text(encoding="utf-8").strip() if path.exists() else fallback


st.title("Community")
st.caption("A season activity feed that celebrates DX without exposing private account or station-list data.")

with st.container(horizontal=True, vertical_alignment="center"):
    st.badge(f"Version {APP_VERSION}", icon=":material/new_releases:", color="blue")
    st.caption("Season 7 staging build")

with st.container(border=True):
    st.subheader("Community activity")
    st.write("Recent aggregate milestones, challenge finishes, and new states/countries/grids will appear here.")
    st.caption("Individual catches are not shared from this page. A personal opt-in control will be added only if individual community sharing is introduced later.")

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
