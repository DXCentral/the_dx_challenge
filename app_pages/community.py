import streamlit as st


st.title("Community")
st.caption("A season activity feed that celebrates DX without exposing private account or station-list data.")

with st.container(border=True):
    st.subheader("Community activity")
    st.write("Recent milestones, challenge finishes, new states/countries/grids, and opt-in shared catches will appear here.")
    st.badge("Opt-in sharing", icon=":material/privacy_tip:", color="blue")

with st.container(border=True):
    st.subheader("Livestream prompts")
    st.write("Announcements and community goals can support the weekly DX livestream without becoming a chat or social network.")

