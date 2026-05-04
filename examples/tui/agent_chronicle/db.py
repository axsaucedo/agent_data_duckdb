"""Shared DuckDB connection and data loading for Agent Chronicle TUI.

Adapted from examples/explorer/db.py, removing Streamlit dependencies.
Uses a simple TTL-based cache for session data.
"""

import os
import time
import logging
from pathlib import Path

import duckdb
import pandas as pd

logger = logging.getLogger(__name__)

# Cache TTL in seconds
CACHE_TTL = 120

_connection: duckdb.DuckDBPyConnection | None = None
_cache: dict[str, tuple[float, pd.DataFrame]] = {}


def _connect() -> duckdb.DuckDBPyConnection:
    if os.environ.get("AGENT_DATA_EXTENSION_PATH"):
        return duckdb.connect(config={"allow_unsigned_extensions": "true"})
    return duckdb.connect()


def _load_agent_data(con: duckdb.DuckDBPyConnection) -> None:
    extension_path = os.environ.get("AGENT_DATA_EXTENSION_PATH")
    if extension_path:
        path = Path(extension_path).expanduser().resolve()
        escaped_path = path.as_posix().replace("'", "''")
        con.execute(f"LOAD '{escaped_path}'")
        return

    con.execute("INSTALL agent_data FROM community")
    con.execute("LOAD agent_data")


def get_connection() -> duckdb.DuckDBPyConnection:
    """Return a DuckDB connection with agent_data extension loaded.

    Re-creates the connection if stale.
    """
    global _connection
    if _connection is not None:
        try:
            _connection.execute("SELECT 1")
            return _connection
        except Exception:
            logger.warning("Stale DuckDB connection, reconnecting")
            _connection = None
            _cache.clear()

    con = _connect()
    _load_agent_data(con)
    _connection = con
    return con


def reset_connection() -> None:
    """Force a fresh connection on next call."""
    global _connection
    _connection = None
    _cache.clear()


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
    """Execute query with retry on connection failure."""
    try:
        return run_query(sql)
    except Exception as e:
        logger.warning("Query failed (%s), retrying with fresh connection", e)
        reset_connection()
        try:
            return run_query(sql)
        except Exception as e2:
            logger.error("Query failed after retry: %s", e2)
            return pd.DataFrame()


def _cached_query(key: str, sql: str) -> pd.DataFrame:
    """Return cached result if fresh, otherwise re-execute."""
    now = time.time()
    if key in _cache:
        ts, df = _cache[key]
        if now - ts < CACHE_TTL:
            return df
    df = _safe_query(sql)
    _cache[key] = (now, df)
    return df


def _threaded_query(sql: str) -> pd.DataFrame:
    """Execute a query in a fresh connection (thread-safe for workers)."""
    con = _connect()
    try:
        _load_agent_data(con)
        return con.execute(sql).df()
    except Exception as e:
        logger.error("Threaded query failed: %s", e)
        return pd.DataFrame()
    finally:
        con.close()


def _run_queries_threaded(queries: dict[str, str]) -> dict[str, pd.DataFrame]:
    """Run multiple queries in a single thread-local connection."""
    con = _connect()
    results: dict[str, pd.DataFrame] = {}
    try:
        _load_agent_data(con)
        for key, sql in queries.items():
            try:
                results[key] = con.execute(sql).df()
            except Exception:
                results[key] = pd.DataFrame()
    except Exception as e:
        logger.error("Threaded queries failed: %s", e)
    finally:
        con.close()
    return results


def load_session_index(path: str) -> pd.DataFrame:
    """Load session summary index with first user message."""
    key = f"session_index:{path}"
    sql = f"""
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
    """
    return _cached_query(key, sql)


def load_session_events(path: str, session_id: str) -> pd.DataFrame:
    """Load all events for a single session, ordered by line number."""
    key = f"session_events:{path}:{session_id}"
    sql = f"""
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
    """
    return _cached_query(key, sql)


def union_from(claude_path: str, copilot_path: str, table: str = "read_conversations") -> str:
    """Build a UNION ALL FROM clause for both sources."""
    return (
        f"(SELECT * FROM {table}(path='{claude_path}') "
        f"UNION ALL SELECT * FROM {table}(path='{copilot_path}'))"
    )


def path_expr(source: str, table: str, claude_path: str, copilot_path: str) -> str:
    """Return a FROM expression based on source selection."""
    if source == "claude":
        return f"{table}(path='{claude_path}')"
    elif source == "copilot":
        return f"{table}(path='{copilot_path}')"
    else:  # both
        return union_from(claude_path, copilot_path, table)
