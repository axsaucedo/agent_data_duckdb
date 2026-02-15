"""agent_data Explorer — Streamlit multi-page application."""

import streamlit as st

st.set_page_config(
    page_title="agent_data Explorer",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🔍 agent_data Explorer")
st.markdown(
    """
Interactive exploration of AI coding agent session data using the
[`agent_data`](https://community-extensions.duckdb.org/extensions/agent_data.html)
DuckDB extension.

**Supported agents:** Claude Code (`~/.claude`) and GitHub Copilot CLI (`~/.copilot`).

---

Use the sidebar to navigate between pages:

- **Session Browser** — Browse, filter and inspect sessions (Chronicle-style)
- **SQL Query** — Run arbitrary SQL queries with sample templates
"""
)

# Eagerly load the extension on first visit
from db import get_connection, get_data_paths

try:
    con = get_connection()
    claude_path, copilot_path = get_data_paths()

    col1, col2 = st.columns(2)
    with col1:
        try:
            sessions = con.execute(
                f"SELECT COUNT(DISTINCT session_id) as n FROM read_conversations(path='{claude_path}')"
            ).fetchone()
            st.metric("Claude Sessions", sessions[0] if sessions else 0)
        except Exception:
            st.metric("Claude Sessions", "N/A")
    with col2:
        try:
            sessions = con.execute(
                f"SELECT COUNT(DISTINCT session_id) as n FROM read_conversations(path='{copilot_path}')"
            ).fetchone()
            st.metric("Copilot Sessions", sessions[0] if sessions else 0)
        except Exception:
            st.metric("Copilot Sessions", "N/A")

except Exception as e:
    st.error(f"Failed to initialize: {e}")
