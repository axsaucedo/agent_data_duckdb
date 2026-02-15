"""Shared DuckDB connection and data loading for the agent_data explorer."""

import os
import logging
import duckdb
import pandas as pd
import streamlit as st

logger = logging.getLogger(__name__)


def get_connection() -> duckdb.DuckDBPyConnection:
    """Return a cached DuckDB connection with the agent_data extension loaded.
    
    Re-creates the connection if the existing one is stale (e.g. after browser refresh).
    """
    con = st.session_state.get("duckdb_con")
    if con is not None:
        try:
            con.execute("SELECT 1")
            return con
        except Exception:
            logger.warning("Stale DuckDB connection detected, reconnecting")
            st.cache_data.clear()
            st.session_state.pop("duckdb_con", None)
    con = duckdb.connect()
    con.execute("INSTALL agent_data FROM community")
    con.execute("LOAD agent_data")
    st.session_state["duckdb_con"] = con
    return con


def get_data_paths() -> tuple[str, str]:
    """Return (claude_path, copilot_path) from env vars or defaults."""
    claude = os.environ.get("AGENT_DATA_CLAUDE_PATH", "~/.claude")
    copilot = os.environ.get("AGENT_DATA_COPILOT_PATH", "~/.copilot")
    return claude, copilot


def run_query(sql: str) -> pd.DataFrame:
    """Execute a SQL query and return results as a DataFrame."""
    con = get_connection()
    return con.execute(sql).df()


def _safe_query(sql: str) -> pd.DataFrame:
    """Execute query with retry on connection failure. Logs errors."""
    try:
        return run_query(sql)
    except Exception as e:
        logger.warning("Query failed (%s), retrying with fresh connection", e)
        # Connection may be stale — force reconnect and clear cache
        st.session_state.pop("duckdb_con", None)
        st.cache_data.clear()
        try:
            return run_query(sql)
        except Exception as e2:
            logger.error("Query failed after retry: %s", e2)
            return pd.DataFrame()


@st.cache_data(ttl=120, show_spinner="Loading sessions…")
def load_session_index(path: str) -> pd.DataFrame:
    """Load session summary index with first user message."""
    return _safe_query(f"""
        WITH sessions AS (
            SELECT
                source,
                session_id,
                project_path,
                slug,
                MIN(timestamp) AS first_ts,
                MAX(timestamp) AS last_ts,
                COUNT(*) AS event_count,
                SUM(CASE WHEN tool_name IS NOT NULL THEN 1 ELSE 0 END) AS tool_calls,
                SUM(COALESCE(input_tokens, 0)) AS total_input_tokens,
                SUM(COALESCE(output_tokens, 0)) AS total_output_tokens
            FROM read_conversations(path='{path}')
            WHERE message_type != '_parse_error'
            GROUP BY source, session_id, project_path, slug
        ),
        first_msgs AS (
            SELECT session_id,
                   message_content AS first_user_message,
                   ROW_NUMBER() OVER (PARTITION BY session_id ORDER BY line_number) AS rn
            FROM read_conversations(path='{path}')
            WHERE message_type = 'user'
              AND message_content IS NOT NULL
              AND message_content NOT LIKE '<local-command%'
              AND message_content NOT LIKE '<command-name>%'
        )
        SELECT s.*, LEFT(fm.first_user_message, 200) AS first_user_message
        FROM sessions s
        LEFT JOIN first_msgs fm ON s.session_id = fm.session_id AND fm.rn = 1
        ORDER BY s.first_ts DESC
    """)


@st.cache_data(ttl=120, show_spinner="Loading session events…")
def load_session_events(path: str, session_id: str) -> pd.DataFrame:
    """Load all events for a single session, ordered by line number."""
    return _safe_query(f"""
        SELECT
            line_number,
            message_type,
            message_role,
            timestamp,
            model,
            tool_name,
            tool_use_id,
            tool_input,
            message_content,
            input_tokens,
            output_tokens,
            cache_creation_tokens,
            cache_read_tokens,
            stop_reason,
            uuid,
            parent_uuid,
            slug,
            git_branch,
            cwd,
            version
        FROM read_conversations(path='{path}')
        WHERE session_id = '{session_id}'
          AND message_type != '_parse_error'
        ORDER BY line_number
    """)
