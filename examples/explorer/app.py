"""Agent Chronicle — Streamlit multi-page application."""

import streamlit as st

st.set_page_config(
    page_title="Agent Chronicle",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

from branding import render_sidebar_branding, render_sidebar_footer, GLOBAL_CSS

st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
render_sidebar_branding()

# ── Navigation (st.Page API — controls sidebar labels) ──────────────────
overview = st.Page("pages/0_Overview.py", title="Overview", icon="📊", default=True)
browser = st.Page("pages/1_Session_Browser.py", title="Session Browser", icon="📋")
sql = st.Page("pages/2_SQL_Query.py", title="SQL Query", icon="🔎")

nav = st.navigation([overview, browser, sql])
nav.run()

render_sidebar_footer()
