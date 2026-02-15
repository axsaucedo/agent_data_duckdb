"""Shared sidebar branding for Agent Chronicle."""

import streamlit as st

APP_TITLE = "🤖 Agent Chronicle"
APP_SUBTITLE = "Powered by agent_data DuckDB extension"
REPO_URL = "https://github.com/axsaucedo/agent_data_duckdb"

# CSS: fix tertiary button hover color (red → gray).
GLOBAL_CSS = """
<style>
/* Fix tertiary button red hover → muted gray */
button[kind="tertiary"]:hover,
button[data-testid="stBaseButton-tertiary"]:hover {
    color: #94a3b8 !important;
    border-color: rgba(148,163,184,0.3) !important;
}
</style>
"""


def render_sidebar_branding():
    """Render the Agent Chronicle sidebar branding and footer."""
    st.sidebar.markdown(
        f"## {APP_TITLE}",
    )
    st.sidebar.caption(APP_SUBTITLE)
    st.sidebar.divider()


def render_sidebar_footer():
    """Render sidebar footer with repo link."""
    st.sidebar.divider()
    st.sidebar.markdown(
        f"<div style='text-align:center; font-size:12px; color:#64748b;'>"
        f"<a href='{REPO_URL}' target='_blank' style='color:#94a3b8;text-decoration:none;'>"
        f"⭐ agent_data on GitHub</a><br>"
        f"<span style='font-size:11px;'>DuckDB extension for AI agent data</span>"
        f"</div>",
        unsafe_allow_html=True,
    )
