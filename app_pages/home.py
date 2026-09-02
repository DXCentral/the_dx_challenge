import streamlit as st

from app_support import challenge_status, get_store
from dxcore.content import active_announcements


st.title("Home")
store = get_store()
user_id = st.session_state.user["user_id"]
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
        st.page_link("app_pages/challenges.py", label="View challenge results", icon=":material/leaderboard:")
    elif [item for item in future if item["type"] == "sprint"]:
        next_challenge = [item for item in future if item["type"] == "sprint"][0]
        st.markdown("No weekly challenge is active.")
        st.caption(f"Next: {next_challenge['name']} · starts {next_challenge['start_utc']:%d %b %Y %H%M UTC}")
    else:
        st.markdown("No weekly challenge is active. Season-long logging remains available.")

st.subheader("Season progress")
logs = store.logs(user_id)
targets = {"MW": ("MW Master", 700), "FM": ("FM Master", 1000), "NWR": ("NWR Master", 100)}
with st.container(horizontal=True):
    for band, (award, target) in targets.items():
        count = (
            int(logs[logs["band"] == band]["station_id"].nunique())
            if not logs.empty
            else 0
        )
        with st.container(border=True, width=300):
            st.markdown(f"**{award}**")
            st.progress(min(count / target, 1.0), text=f"{count:,} of {target:,} unique stations")
            if st.button(
                "View award details",
                icon=":material/military_tech:",
                key=f"home_award_{band}",
            ):
                st.session_state.selected_award = f"{band} · {award}"
                st.switch_page("app_pages/awards.py")

st.subheader("Announcements")
announcements = active_announcements(store.announcements(active_only=True))
for announcement in announcements.to_dict("records"):
    with st.container(border=True):
        st.markdown(f"**{announcement['title']}**")
        st.write(announcement["body"])
        if announcement.get("start_utc"):
            st.caption(f"Published {announcement['start_utc']}")
if announcements.empty:
    st.caption("No active announcements.")
