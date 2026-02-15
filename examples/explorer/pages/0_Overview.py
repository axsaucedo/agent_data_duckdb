"""Overview — Agent Chronicle dashboard with charts and metrics."""

import streamlit as st
import pandas as pd
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import get_connection, get_data_paths

st.title("🤖 Agent Chronicle")
st.markdown(
    "Interactive exploration of AI coding agent session data using the "
    "[`agent_data`](https://community-extensions.duckdb.org/extensions/agent_data.html) "
    "DuckDB extension.  Use the sidebar to navigate between pages."
)


def _safe_query(con, sql: str) -> pd.DataFrame:
    try:
        return con.execute(sql).fetchdf()
    except Exception:
        return pd.DataFrame()


def _union_from(claude_path: str, copilot_path: str, table: str) -> str:
    return (
        f"(SELECT * FROM {table}(path='{claude_path}') "
        f"UNION ALL SELECT * FROM {table}(path='{copilot_path}'))"
    )


try:
    con = get_connection()
    claude_path, copilot_path = get_data_paths()
    FROM = _union_from(claude_path, copilot_path, "read_conversations")

    # ── Key metrics row ─────────────────────────────────────────────────
    metrics_query = f"""
    SELECT
        source,
        COUNT(DISTINCT session_id) AS sessions,
        COUNT(*) AS messages
    FROM {FROM} t
    GROUP BY source
    """
    metrics_df = _safe_query(con, metrics_query)

    m1, m2, m3, m4 = st.columns(4)
    claude_row = metrics_df[metrics_df["source"] == "claude"] if not metrics_df.empty else pd.DataFrame()
    copilot_row = metrics_df[metrics_df["source"] == "copilot"] if not metrics_df.empty else pd.DataFrame()

    m1.metric("Claude Sessions", int(claude_row["sessions"].iloc[0]) if not claude_row.empty else 0)
    m2.metric("Claude Messages", int(claude_row["messages"].iloc[0]) if not claude_row.empty else 0)
    m3.metric("Copilot Sessions", int(copilot_row["sessions"].iloc[0]) if not copilot_row.empty else 0)
    m4.metric("Copilot Messages", int(copilot_row["messages"].iloc[0]) if not copilot_row.empty else 0)

    with st.expander("View query"):
        st.code(metrics_query.strip(), language="sql")

    st.divider()

    # ── Charts ──────────────────────────────────────────────────────────
    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        st.subheader("Messages by Source")
        source_query = f"""
        SELECT source, COUNT(*) AS messages
        FROM {FROM} t
        GROUP BY source
        """
        source_df = _safe_query(con, source_query)
        if not source_df.empty:
            st.bar_chart(source_df.set_index("source"))
        else:
            st.info("No data available")
        with st.expander("View query"):
            st.code(source_query.strip(), language="sql")

    with chart_col2:
        st.subheader("Message Types")
        types_query = f"""
        SELECT message_type, COUNT(*) AS count
        FROM {FROM} t
        WHERE message_type IS NOT NULL
        GROUP BY message_type
        ORDER BY count DESC
        LIMIT 10
        """
        types_df = _safe_query(con, types_query)
        if not types_df.empty:
            st.bar_chart(types_df.set_index("message_type"))
        else:
            st.info("No data available")
        with st.expander("View query"):
            st.code(types_query.strip(), language="sql")

    chart_col3, chart_col4 = st.columns(2)

    with chart_col3:
        st.subheader("Daily Activity")
        daily_query = f"""
        SELECT
            CAST(timestamp AS DATE) AS day,
            source,
            COUNT(*) AS messages
        FROM {FROM} t
        WHERE timestamp IS NOT NULL
        GROUP BY day, source
        ORDER BY day
        """
        daily_df = _safe_query(con, daily_query)
        if not daily_df.empty and "day" in daily_df.columns:
            pivot = daily_df.pivot_table(
                index="day", columns="source", values="messages", aggfunc="sum"
            ).fillna(0)
            st.line_chart(pivot)
        else:
            st.info("No timestamp data available")
        with st.expander("View query"):
            st.code(daily_query.strip(), language="sql")

    with chart_col4:
        st.subheader("Top Projects")
        projects_query = f"""
        SELECT
            COALESCE(SPLIT_PART(project_path, '/', -1), 'unknown') AS project,
            COUNT(*) AS messages
        FROM {FROM} t
        WHERE project_path IS NOT NULL AND project_path != ''
        GROUP BY project
        ORDER BY messages DESC
        LIMIT 10
        """
        projects_df = _safe_query(con, projects_query)
        if not projects_df.empty:
            st.bar_chart(projects_df.set_index("project"))
        else:
            st.info("No project data available")
        with st.expander("View query"):
            st.code(projects_query.strip(), language="sql")

    st.subheader("Token Usage by Source")
    tokens_query = f"""
    SELECT
        source,
        SUM(COALESCE(input_tokens, 0)) AS input_tokens,
        SUM(COALESCE(output_tokens, 0)) AS output_tokens
    FROM {FROM} t
    GROUP BY source
    """
    tokens_df = _safe_query(con, tokens_query)
    if not tokens_df.empty and tokens_df[["input_tokens", "output_tokens"]].sum().sum() > 0:
        st.bar_chart(tokens_df.set_index("source"))
    else:
        st.info("No token usage data available")
    with st.expander("View query"):
        st.code(tokens_query.strip(), language="sql")

    st.subheader("Top Tools Used")
    tools_query = f"""
    SELECT tool_name, COUNT(*) AS uses
    FROM {FROM} t
    WHERE tool_name IS NOT NULL AND tool_name != ''
    GROUP BY tool_name
    ORDER BY uses DESC
    LIMIT 15
    """
    tools_df = _safe_query(con, tools_query)
    if not tools_df.empty:
        st.bar_chart(tools_df.set_index("tool_name"))
    else:
        st.info("No tool usage data available")
    with st.expander("View query"):
        st.code(tools_query.strip(), language="sql")

except Exception as e:
    st.error(f"Failed to initialize: {e}")
    st.exception(e)
