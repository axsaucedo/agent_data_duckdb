"""Shared DuckDB connection for the agent_data explorer."""

import os
import duckdb
import streamlit as st


def get_connection() -> duckdb.DuckDBPyConnection:
    """Return a cached DuckDB connection with the agent_data extension loaded."""
    if "duckdb_con" not in st.session_state:
        con = duckdb.connect()
        con.execute("INSTALL agent_data FROM community")
        con.execute("LOAD agent_data")
        st.session_state["duckdb_con"] = con
    return st.session_state["duckdb_con"]


def get_data_paths() -> tuple[str, str]:
    """Return (claude_path, copilot_path) from env vars or defaults."""
    claude = os.environ.get("AGENT_DATA_CLAUDE_PATH", "~/.claude")
    copilot = os.environ.get("AGENT_DATA_COPILOT_PATH", "~/.copilot")
    return claude, copilot


def run_query(sql: str) -> "pandas.DataFrame":
    """Execute a SQL query and return results as a DataFrame."""
    con = get_connection()
    return con.execute(sql).df()
