"""SQL Query — Interactive SQL query interface with samples and query builder.

Run arbitrary SQL queries against your agent data using the agent_data
DuckDB extension. Includes categorized sample queries and a basic query builder.
"""

import streamlit as st
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import get_connection, get_data_paths, run_query

st.title("🔎 SQL Query")

con = get_connection()
claude_path, copilot_path = get_data_paths()


# ---------------------------------------------------------------------------
# Helper: build path expression based on source choice
# ---------------------------------------------------------------------------
def _path_expr(source: str, table: str = "read_conversations") -> str:
    """Return a FROM clause with path parameter based on source selection."""
    if source == "Claude":
        return f"{table}(path='{claude_path}')"
    elif source == "Copilot":
        return f"{table}(path='{copilot_path}')"
    else:  # Both
        return (
            f"(\n    SELECT * FROM {table}(path='{claude_path}')\n"
            f"    UNION ALL\n"
            f"    SELECT * FROM {table}(path='{copilot_path}')\n)"
        )


# ---------------------------------------------------------------------------
# Sample queries (templates with {FROM} placeholder)
# ---------------------------------------------------------------------------
SAMPLE_QUERIES = {
    "📊 Overview": {
        "Session overview": """SELECT source, session_id, project_path,
       COUNT(*) AS msg_count,
       MIN(timestamp) AS started,
       MAX(timestamp) AS ended
FROM {FROM}
WHERE message_type != '_parse_error'
GROUP BY source, session_id, project_path
ORDER BY started DESC
LIMIT 50""",
        "Source comparison": """SELECT source,
       COUNT(DISTINCT session_id) AS sessions,
       COUNT(*) AS messages
FROM {FROM}
GROUP BY source""",
        "Daily activity": """SELECT date, message_count, session_count, tool_call_count
FROM {STATS_FROM}
ORDER BY date DESC
LIMIT 30""",
    },
    "🔧 Tool Analysis": {
        "Tool usage frequency": """SELECT tool_name, COUNT(*) AS uses
FROM {FROM}
WHERE tool_name IS NOT NULL
GROUP BY tool_name
ORDER BY uses DESC
LIMIT 20""",
        "Tools per session": """SELECT session_id,
       COUNT(DISTINCT tool_name) AS unique_tools,
       COUNT(CASE WHEN tool_name IS NOT NULL THEN 1 END) AS total_tool_calls
FROM {FROM}
GROUP BY session_id
ORDER BY total_tool_calls DESC
LIMIT 20""",
    },
    "💬 Conversations": {
        "Message types distribution": """SELECT source, message_type, COUNT(*) AS count
FROM {FROM}
WHERE message_type != '_parse_error'
GROUP BY source, message_type
ORDER BY source, count DESC""",
        "Longest sessions": """SELECT source, session_id, project_path,
       COUNT(*) AS messages,
       SUM(COALESCE(input_tokens, 0)) AS total_input_tokens,
       SUM(COALESCE(output_tokens, 0)) AS total_output_tokens
FROM {FROM}
WHERE message_type != '_parse_error'
GROUP BY source, session_id, project_path
ORDER BY messages DESC
LIMIT 10""",
        "Models used": """SELECT model, COUNT(*) AS messages,
       SUM(COALESCE(input_tokens, 0)) AS input_tokens,
       SUM(COALESCE(output_tokens, 0)) AS output_tokens
FROM {FROM}
WHERE model IS NOT NULL
GROUP BY model
ORDER BY messages DESC""",
    },
    "📝 Todos & Plans": {
        "Active todos": """SELECT source, session_id, content, status
FROM {TODOS_FROM}
WHERE status != 'completed'
ORDER BY item_index""",
        "Todo status distribution": """SELECT source, status, COUNT(*) AS count
FROM {TODOS_FROM}
GROUP BY source, status
ORDER BY count DESC""",
        "Plans overview": """SELECT source, session_id, plan_name, file_name, file_size
FROM {PLANS_FROM}
ORDER BY file_size DESC""",
    },
    "📜 History": {
        "Recent commands": """SELECT source, display, timestamp_ms, project, session_id
FROM {HISTORY_FROM}
ORDER BY line_number DESC
LIMIT 50""",
    },
    "🔗 Joins": {
        "Sessions with todos": """SELECT
    c.source,
    c.session_id,
    c.project_path,
    COUNT(DISTINCT c.uuid) AS messages,
    COUNT(DISTINCT t.content) AS todos
FROM {FROM} c
LEFT JOIN {TODOS_FROM} t
    ON c.session_id = t.session_id AND c.source = t.source
GROUP BY c.source, c.session_id, c.project_path
HAVING todos > 0
ORDER BY todos DESC""",
        "Sessions with plans": """SELECT
    c.source,
    c.session_id,
    c.slug,
    p.plan_name,
    p.file_size,
    COUNT(*) AS messages
FROM {FROM} c
JOIN {PLANS_FROM} p
    ON c.slug = p.plan_name AND c.source = p.source
GROUP BY c.source, c.session_id, c.slug, p.plan_name, p.file_size
ORDER BY messages DESC""",
    },
}


def _render_query(template: str, source: str) -> str:
    """Replace {FROM}, {STATS_FROM}, etc. placeholders with path expressions."""
    return (
        template
        .replace("{FROM}", _path_expr(source, "read_conversations"))
        .replace("{STATS_FROM}", _path_expr(source, "read_stats"))
        .replace("{TODOS_FROM}", _path_expr(source, "read_todos"))
        .replace("{PLANS_FROM}", _path_expr(source, "read_plans"))
        .replace("{HISTORY_FROM}", _path_expr(source, "read_history"))
    )


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
if "sql_auto_run" not in st.session_state:
    st.session_state["sql_auto_run"] = False

# Use the text area widget key directly for state
EDITOR_KEY = "sql_editor"
if EDITOR_KEY not in st.session_state:
    st.session_state[EDITOR_KEY] = "SELECT * FROM read_conversations() LIMIT 10"

# ---------------------------------------------------------------------------
# Sidebar: source selector, sample queries, query builder
# ---------------------------------------------------------------------------
st.sidebar.header("Data Source")
sql_source = st.sidebar.radio(
    "Source for queries",
    ["Claude", "Copilot", "Both"],
    index=0,
    horizontal=True,
    help="Controls which data path is used in sample queries and query builder",
)

st.sidebar.divider()
st.sidebar.header("Sample Queries")

categories = ["Select…"] + list(SAMPLE_QUERIES.keys())
selected_category = st.sidebar.selectbox("Category", categories, index=0)

if selected_category != "Select…":
    st.sidebar.markdown("**Click a query to load it:**")
    for query_name, query_template in SAMPLE_QUERIES[selected_category].items():
        if st.sidebar.button(query_name, key=f"sample_{query_name}", use_container_width=True):
            rendered = _render_query(query_template, sql_source)
            st.session_state[EDITOR_KEY] = rendered
            st.session_state["sql_auto_run"] = True
            st.rerun()

st.sidebar.divider()
st.sidebar.header("Query Builder")

TABLE_OPTIONS = {
    "read_conversations": "read_conversations",
    "read_plans": "read_plans",
    "read_todos": "read_todos",
    "read_history": "read_history",
    "read_stats": "read_stats",
}
selected_table_name = st.sidebar.selectbox("Table", list(TABLE_OPTIONS.keys()))

COLUMN_MAP = {
    "read_conversations": [
        "source", "session_id", "project_path", "message_type",
        "message_role", "timestamp", "model", "tool_name",
        "message_content", "input_tokens", "output_tokens",
    ],
    "read_plans": [
        "source", "session_id", "plan_name", "file_name", "file_size", "content",
    ],
    "read_todos": [
        "source", "session_id", "content", "status", "item_index",
    ],
    "read_history": [
        "source", "line_number", "display", "timestamp_ms", "project", "session_id",
    ],
    "read_stats": [
        "source", "date", "message_count", "session_count", "tool_call_count",
    ],
}

available_columns = COLUMN_MAP.get(selected_table_name, ["*"])
selected_columns = st.sidebar.multiselect(
    "Columns", available_columns, default=available_columns
)

where_clause = st.sidebar.text_input("WHERE clause (optional)", "", help="e.g. source='claude' AND message_type='user'")
order_by = st.sidebar.text_input("ORDER BY (optional)", "", help="e.g. timestamp DESC")
limit_val = st.sidebar.number_input("LIMIT (0 = no limit)", min_value=0, max_value=10000, value=100)

if st.sidebar.button("Replace & Run", type="primary", use_container_width=True):
    cols = ", ".join(selected_columns) if selected_columns else "*"
    from_expr = _path_expr(sql_source, selected_table_name)
    built_sql = f"SELECT {cols}\nFROM {from_expr}"
    if where_clause:
        built_sql += f"\nWHERE {where_clause}"
    if order_by:
        built_sql += f"\nORDER BY {order_by}"
    if limit_val > 0:
        built_sql += f"\nLIMIT {limit_val}"
    st.session_state[EDITOR_KEY] = built_sql
    st.session_state["sql_auto_run"] = True
    st.rerun()

# ---------------------------------------------------------------------------
# Main: SQL editor and results
# ---------------------------------------------------------------------------

sql_input = st.text_area(
    "SQL Query",
    height=200,
    key=EDITOR_KEY,
    help="Write any SQL query using agent_data functions. Results are displayed below.",
)

col1, col2 = st.columns([1, 5])
with col1:
    run_btn = st.button("▶ Run", type="primary")

should_run = run_btn or st.session_state.get("sql_auto_run", False)
st.session_state["sql_auto_run"] = False

if should_run and sql_input.strip():
    try:
        with st.spinner("Executing query..."):
            result_df = run_query(sql_input)
        st.success(f"✅ {len(result_df)} rows returned")
        st.dataframe(result_df, use_container_width=True, hide_index=True)

        csv = result_df.to_csv(index=False)
        st.download_button(
            "📥 Download CSV",
            data=csv,
            file_name="query_results.csv",
            mime="text/csv",
        )
    except Exception as e:
        st.error(f"Query failed: {e}")

# ---------------------------------------------------------------------------
# Quick reference
# ---------------------------------------------------------------------------
with st.expander("📖 Quick Reference"):
    st.markdown("""
### Available Functions

| Function | Description |
|----------|-------------|
| `read_conversations([path], [source])` | Conversation/event data |
| `read_plans([path], [source])` | Plan files |
| `read_todos([path], [source])` | Todo/checklist items |
| `read_history([path], [source])` | Command history |
| `read_stats([path], [source])` | Daily activity stats |

### Parameters

- **`path`** — Data directory (default: `~/.claude`). Auto-detected from structure.
- **`source`** — Force provider: `'claude'` or `'copilot'`

### Join Keys

| Join | Key | Notes |
|------|-----|-------|
| conversations ↔ history | `session_id` | Same source |
| conversations ↔ todos | `session_id` | Same source |
| conversations ↔ plans | `slug` = `plan_name` | Claude only |

### Tips

- Filter parse errors: `WHERE message_type != '_parse_error'`
- Cross-source: `UNION ALL` queries from different paths
- Every table has `source` as first column
""")
