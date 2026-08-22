import streamlit as st

from app_support import (
    initialize_app_state,
    maybe_show_walkthrough,
    render_app_bar,
    render_user_theme,
    require_authentication,
)


def main() -> None:
    st.set_page_config(
        page_title="The DX Challenge · Season 7",
        page_icon=":material/radio:",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    require_authentication()
    initialize_app_state()
    render_user_theme()

    pages = [
        st.Page("app_pages/home.py", title="Home", icon=":material/home:", default=True),
        st.Page("app_pages/bandscan.py", title="Bandscan", icon=":material/grid_view:"),
        st.Page("app_pages/log_entry.py", title="Log entry", icon=":material/add_circle:"),
        st.Page("app_pages/logbook.py", title="My logbook", icon=":material/table_rows:"),
        st.Page("app_pages/challenges.py", title="Challenges", icon=":material/calendar_month:"),
        st.Page("app_pages/awards.py", title="Awards", icon=":material/military_tech:"),
        st.Page("app_pages/leaderboards.py", title="Leaderboards", icon=":material/leaderboard:"),
        st.Page("app_pages/stats.py", title="Stats", icon=":material/analytics:"),
        st.Page("app_pages/community.py", title="Community", icon=":material/groups:"),
        st.Page("app_pages/profile.py", title="Profile settings", icon=":material/settings:"),
    ]

    navigation = st.navigation(pages, position="top")
    render_app_bar()
    maybe_show_walkthrough()
    navigation.run()


if __name__ == "__main__":
    main()
