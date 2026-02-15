"""SQL Query — Interactive SQL query interface with samples and query builder.

Run arbitrary SQL queries against your agent data using the agent_data
DuckDB extension. Includes categorized sample queries and a basic query builder.
"""

import streamlit as st
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import get_connection, get_data_paths, run_query

st.set_page_config(page_title="SQL Query", page_icon="🔎", layout="wide")
st.title("🔎 SQL Query")

con = get_connection()
claude_path, copilot_path = get_data_paths()

# ---------------------------------------------------------------------------
# Sample queries
# ---------------------------------------------------------------------------
SAMPLE_QUERIES = {
    "📊 Overview": {
        "Session overview": f"""SELECT source, session_id, project_path,
       COUNT(*) AS msg_count,
       MIN(timestamp) AS started,
       MAX(timestamp) AS ended
FROM read_conversations()
WHERE message_type != '_parse_error'
GROUP BY source, session_id, project_path
ORDER BY started DESC
LIMIT 50""",
        "Source comparison": f"""SELECT source,
       COUNT(DISTINCT session_id) AS sessions,
       COUNT(*) AS messages
FROM (
    SELECT * FROM read_conversations(path='{claude_path}')
    UNION ALL
    SELECT * FROM read_conversations(path='{copilot_path}')
)
GROUP BY source""",
        "Daily activity": """SELECT date, message_count, session_count, tool_call_count
FROM read_stats()
ORDER BY date DESC
LIMIT 30""",
    },
    "🔧 Tool Analysis": {
        "Tool usage frequency": """SELECT tool_name, COUNT(*) AS uses
FROM read_conversations()
WHERE tool_name IS NOT NULL
GROUP BY tool_name
ORDER BY uses DESC
LIMIT 20""",
        "Tools per session": """SELECT session_id,
       COUNT(DISTINCT tool_name) AS unique_tools,
       COUNT(CASE WHEN tool_name IS NOT NULL THEN 1 END) AS total_tool_calls
FROM read_conversations()
GROUP BY session_id
ORDER BY total_tool_calls DESC
LIMIT 20""",
    },
    "💬 Conversations": {
        "Message types distribution": """SELECT source, message_type, COUNT(*) AS count
FROM read_conversations()
WHERE message_type != '_parse_error'
GROUP BY source, message_type
ORDER BY source, count DESC""",
        "Longest sessions": """SELECT source, session_id, project_path,
       COUNT(*) AS messages,
       SUM(COALESCE(input_tokens, 0)) AS total_input_tokens,
       SUM(COALESCE(output_tokens, 0)) AS total_output_tokens
FROM read_conversations()
WHERE message_type != '_parse_error'
GROUP BY source, session_id, project_path
ORDER BY messages DESC
LIMIT 10""",
        "Models used": """SELECT model, COUNT(*) AS messages,
       SUM(COALESCE(input_tokens, 0)) AS input_tokens,
       SUM(COALESCE(output_tokens, 0)) AS output_tokens
FROM read_conversations()
WHERE model IS NOT NULL
GROUP BY model
ORDER BY messages DESC""",
    },
    "📝 Todos & Plans": {
        "Active todos": """SELECT source, session_id, content, status
FROM read_todos()
WHERE status != 'completed'
ORDER BY item_index""",
        "Todo status distribution": """SELECT source, status, COUNT(*) AS count
FROM read_todos()
GROUP BY source, status
ORDER BY count DESC""",
        "Plans overview": """SELECT source, session_id, plan_name, file_name, file_size
FROM read_plans()
ORDER BY file_size DESC""",
    },
    "📜 History": {
        "Recent commands": """SELECT source, display, timestamp_ms, project, session_id
FROM read_history()
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
FROM read_conversations() c
LEFT JOIN read_todos() t
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
FROM read_conversations() c
JOIN read_plans() p
    ON c.slug = p.plan_name AND c.source = p.source
GROUP BY c.source, c.session_id, c.slug, p.plan_name, p.file_size
ORDER BY messages DESC""",
    },
}

# ---------------------------------------------------------------------------
# Sidebar: sample queries and query builder
# ---------------------------------------------------------------------------
st.sidebar.header("Sample Queries")

selected_category = st.sidebar.selectbox(
    "Category", list(SAMPLE_QUERIES.keys())
)
category_queries = SAMPLE_QUERIES[selected_category]
selected_sample = st.sidebar.selectbox(
    "Query", ["(none)"] + list(category_queries.keys())
)

if selected_sample != "(none)":
    sample_sql = category_queries[selected_sample]
else:
    sample_sql = None

st.sidebar.divider()
st.sidebar.header("Query Builder")

table_options = [
    "read_conversations()",
    "read_plans()",
    "read_todos()",
    "read_history()",
    "read_stats()",
]
selected_table = st.sidebar.selectbox("Table", table_options)

COLUMN_MAP = {
    "read_conversations()": [
        "source", "session_id", "project_path", "message_type",
        "message_role", "timestamp", "model", "tool_name",
        "message_content", "input_tokens", "output_tokens",
    ],
    "read_plans()": [
        "source", "session_id", "plan_name", "file_name", "file_size", "content",
    ],
    "read_todos()": [
        "source", "session_id", "content", "status", "item_index",
    ],
    "read_history()": [
        "source", "line_number", "display", "timestamp_ms", "project", "session_id",
    ],
    "read_stats()": [
        "source", "date", "message_count", "session_count", "tool_call_count",
    ],
}

available_columns = COLUMN_MAP.get(selected_table, ["*"])
selected_columns = st.sidebar.multiselect(
    "Columns", available_columns, default=["source"]
)

where_clause = st.sidebar.text_input("WHERE clause (optional)", "")
order_by = st.sidebar.text_input("ORDER BY (optional)", "")
limit_val = st.sidebar.number_input("LIMIT", min_value=0, max_value=10000, value=100)

build_query = st.sidebar.button("Build Query")

# ---------------------------------------------------------------------------
# Main: SQL editor and results
# ---------------------------------------------------------------------------

# Determine initial query
if build_query:
    cols = ", ".join(selected_columns) if selected_columns else "*"
    built_sql = f"SELECT {cols}\nFROM {selected_table}"
    if where_clause:
        built_sql += f"\nWHERE {where_clause}"
    if order_by:
        built_sql += f"\nORDER BY {order_by}"
    if limit_val > 0:
        built_sql += f"\nLIMIT {limit_val}"
    default_sql = built_sql
elif sample_sql:
    default_sql = sample_sql
else:
    default_sql = "SELECT * FROM read_conversations() LIMIT 10"

sql_input = st.text_area(
    "SQL Query",
    value=default_sql,
    height=200,
    help="Write any SQL query using agent_data functions. Results are displayed below.",
)

col1, col2 = st.columns([1, 5])
with col1:
    run_btn = st.button("▶ Run", type="primary")

if run_btn and sql_input.strip():
    try:
        with st.spinner("Executing query..."):
            result_df = run_query(sql_input)
        st.success(f"✅ {len(result_df)} rows returned")
        st.dataframe(result_df, use_container_width=True, hide_index=True)

        # Download button
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
