import streamlit as st

from app_support import bandscan_progress, challenge_status, current_location
from dxcore.content import load_announcements


st.title("Home")
location = current_location()
current, _, future = challenge_status()

with st.container(border=True):
    st.subheader("Current DX Challenge")
    active_sprints = [item for item in current if item["type"] == "sprint"]
    if active_sprints:
        challenge = active_sprints[0]
        st.markdown(f"**{challenge['name']}**")
        st.caption(
            f"{challenge['start_utc']:%d %b %Y %H%M UTC} through {challenge['end_utc']:%d %b %Y %H%M UTC}"
        )
        st.page_link("app_pages/leaderboards.py", label="View challenge leaderboard", icon=":material/leaderboard:")
    elif [item for item in future if item["type"] == "sprint"]:
        next_challenge = [item for item in future if item["type"] == "sprint"][0]
        st.markdown("No weekly challenge is active.")
        st.caption(f"Next: {next_challenge['name']} · starts {next_challenge['start_utc']:%d %b %Y %H%M UTC}")
    else:
        st.markdown("No weekly challenge is active. Season-long logging remains available.")

st.subheader("Readiness")
if location is None:
    st.info("Create your first QTH in Profile Settings to begin a bandscan.", icon=":material/location_on:")
else:
    with st.container(horizontal=True):
        for band in ("MW", "FM", "NWR"):
            completed, total, ratio = bandscan_progress(str(location["location_id"]), band)
            with st.container(border=True, width=300):
                st.markdown(f"**{band} readiness**")
                st.progress(ratio, text=f"{completed} of {total} channels reviewed")
                if ratio == 1:
                    st.badge("Unlocked", icon=":material/lock_open:", color="green")
                else:
                    st.badge("Baseline required", icon=":material/pending:", color="orange")

st.subheader("Announcements")
announcements = load_announcements()
for announcement in announcements.to_dict("records"):
    with st.container(border=True):
        st.markdown(f"**{announcement['title']}**")
        st.write(announcement["message"])
        if announcement.get("start_utc"):
            st.caption(f"Published {announcement['start_utc']}")
if announcements.empty:
    st.caption("No active announcements.")
