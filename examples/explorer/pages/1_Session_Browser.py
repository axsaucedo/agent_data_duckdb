"""Session Browser — Chronicle-style session explorer.

Browse sessions with filtering, view conversation timelines,
inspect message details and metadata.
"""

import streamlit as st
import pandas as pd
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import get_connection, get_data_paths

st.set_page_config(page_title="Session Browser", page_icon="📋", layout="wide")
st.title("📋 Session Browser")

con = get_connection()
claude_path, copilot_path = get_data_paths()

# ---------------------------------------------------------------------------
# Load session summary
# ---------------------------------------------------------------------------
@st.cache_data(ttl=60)
def load_sessions():
    """Load session summaries from all configured sources."""
    parts = []
    for path in (claude_path, copilot_path):
        try:
            df = con.execute(f"""
                SELECT
                    source,
                    session_id,
                    project_path,
                    slug,
                    model,
                    MIN(timestamp) AS first_message,
                    MAX(timestamp) AS last_message,
                    COUNT(*) AS message_count,
                    COUNT(DISTINCT message_type) AS type_count,
                    SUM(CASE WHEN tool_name IS NOT NULL THEN 1 ELSE 0 END) AS tool_calls,
                    SUM(COALESCE(input_tokens, 0)) AS total_input_tokens,
                    SUM(COALESCE(output_tokens, 0)) AS total_output_tokens
                FROM read_conversations(path='{path}')
                WHERE message_type != '_parse_error'
                GROUP BY source, session_id, project_path, slug, model
                ORDER BY first_message DESC
            """).df()
            parts.append(df)
        except Exception:
            pass
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True)


sessions_df = load_sessions()

if sessions_df.empty:
    st.warning("No sessions found. Check that your data paths are correct.")
    st.info(f"Claude path: `{claude_path}` | Copilot path: `{copilot_path}`")
    st.stop()

# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------
st.sidebar.header("Filters")

sources = sorted(sessions_df["source"].dropna().unique())
selected_source = st.sidebar.multiselect("Source", sources, default=sources)

projects = sorted(sessions_df["project_path"].dropna().unique())
selected_projects = st.sidebar.multiselect("Project", projects, default=[])

models = sorted(sessions_df["model"].dropna().unique())
selected_model = st.sidebar.multiselect("Model", models, default=[])

min_messages = st.sidebar.slider(
    "Min messages", 0, int(sessions_df["message_count"].max()), 0
)

# Apply filters
filtered = sessions_df[sessions_df["source"].isin(selected_source)]
if selected_projects:
    filtered = filtered[filtered["project_path"].isin(selected_projects)]
if selected_model:
    filtered = filtered[filtered["model"].isin(selected_model)]
filtered = filtered[filtered["message_count"] >= min_messages]

# ---------------------------------------------------------------------------
# Session list
# ---------------------------------------------------------------------------
st.subheader(f"Sessions ({len(filtered)})")

display_cols = [
    "source", "session_id", "project_path", "model",
    "first_message", "last_message", "message_count",
    "tool_calls", "total_input_tokens", "total_output_tokens",
]
display_df = filtered[display_cols].copy()
display_df["session_id_short"] = display_df["session_id"].str[:12] + "…"

st.dataframe(
    display_df[
        ["source", "session_id_short", "project_path", "model",
         "first_message", "last_message", "message_count",
         "tool_calls", "total_input_tokens", "total_output_tokens"]
    ],
    use_container_width=True,
    hide_index=True,
    column_config={
        "session_id_short": st.column_config.TextColumn("Session"),
        "source": st.column_config.TextColumn("Source"),
        "project_path": st.column_config.TextColumn("Project"),
        "model": st.column_config.TextColumn("Model"),
        "first_message": st.column_config.TextColumn("Started"),
        "last_message": st.column_config.TextColumn("Ended"),
        "message_count": st.column_config.NumberColumn("Messages"),
        "tool_calls": st.column_config.NumberColumn("Tool Calls"),
        "total_input_tokens": st.column_config.NumberColumn("Input Tokens"),
        "total_output_tokens": st.column_config.NumberColumn("Output Tokens"),
    },
)

# ---------------------------------------------------------------------------
# Session detail
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Session Detail")

session_options = {
    f"[{row['source']}] {row['session_id'][:12]}… — {row['project_path'] or 'unknown'} ({row['message_count']} msgs)": row["session_id"]
    for _, row in filtered.iterrows()
    if row["session_id"]
}

if not session_options:
    st.info("No sessions match the current filters.")
    st.stop()

selected_label = st.selectbox("Select a session to inspect", list(session_options.keys()))
selected_session_id = session_options[selected_label]

# Determine which path to query
session_source = filtered[filtered["session_id"] == selected_session_id]["source"].iloc[0]
source_path = claude_path if session_source == "claude" else copilot_path


@st.cache_data(ttl=60)
def load_session_messages(session_id: str, path: str):
    """Load all messages for a specific session."""
    return con.execute(f"""
        SELECT
            line_number, message_type, message_role, timestamp,
            model, tool_name, tool_use_id,
            CASE WHEN LENGTH(message_content) > 500
                 THEN SUBSTRING(message_content, 1, 500) || '…'
                 ELSE message_content END AS message_preview,
            message_content,
            input_tokens, output_tokens,
            cache_creation_tokens, cache_read_tokens,
            stop_reason, uuid, parent_uuid,
            slug, git_branch, cwd, version
        FROM read_conversations(path='{path}')
        WHERE session_id = '{session_id}'
          AND message_type != '_parse_error'
        ORDER BY line_number
    """).df()


messages_df = load_session_messages(selected_session_id, source_path)

if messages_df.empty:
    st.warning("No messages found for this session.")
    st.stop()

# Session metadata
meta_col1, meta_col2, meta_col3, meta_col4 = st.columns(4)
with meta_col1:
    st.metric("Messages", len(messages_df))
with meta_col2:
    tool_count = messages_df["tool_name"].notna().sum()
    st.metric("Tool Calls", int(tool_count))
with meta_col3:
    total_in = messages_df["input_tokens"].sum()
    st.metric("Input Tokens", f"{int(total_in):,}" if pd.notna(total_in) else "N/A")
with meta_col4:
    total_out = messages_df["output_tokens"].sum()
    st.metric("Output Tokens", f"{int(total_out):,}" if pd.notna(total_out) else "N/A")

# Show session metadata in expander
with st.expander("Session Metadata"):
    meta_fields = {}
    for col in ["slug", "git_branch", "cwd", "version", "model"]:
        vals = messages_df[col].dropna().unique()
        if len(vals) > 0:
            meta_fields[col] = ", ".join(str(v) for v in vals)
    if meta_fields:
        for k, v in meta_fields.items():
            st.text(f"{k}: {v}")
    else:
        st.text("No additional metadata available.")

# Tool usage breakdown
tool_usage = messages_df[messages_df["tool_name"].notna()]["tool_name"].value_counts()
if not tool_usage.empty:
    with st.expander("Tool Usage Breakdown"):
        st.bar_chart(tool_usage)

# Message timeline
st.subheader("Conversation Timeline")

type_filter = st.multiselect(
    "Filter by message type",
    sorted(messages_df["message_type"].unique()),
    default=[],
)

timeline_df = messages_df.copy()
if type_filter:
    timeline_df = timeline_df[timeline_df["message_type"].isin(type_filter)]

# Display timeline as table
st.dataframe(
    timeline_df[
        ["line_number", "timestamp", "message_type", "message_role",
         "tool_name", "message_preview", "input_tokens", "output_tokens"]
    ],
    use_container_width=True,
    hide_index=True,
    column_config={
        "line_number": st.column_config.NumberColumn("#"),
        "timestamp": st.column_config.TextColumn("Time"),
        "message_type": st.column_config.TextColumn("Type"),
        "message_role": st.column_config.TextColumn("Role"),
        "tool_name": st.column_config.TextColumn("Tool"),
        "message_preview": st.column_config.TextColumn("Content", width="large"),
        "input_tokens": st.column_config.NumberColumn("In Tokens"),
        "output_tokens": st.column_config.NumberColumn("Out Tokens"),
    },
)

# Message detail
st.divider()
st.subheader("Message Detail")

msg_options = {
    f"#{row['line_number']} [{row['message_type']}] {(row['message_preview'] or '')[:60]}": idx
    for idx, row in timeline_df.iterrows()
}

if msg_options:
    selected_msg_label = st.selectbox("Select a message", list(msg_options.keys()))
    msg_idx = msg_options[selected_msg_label]
    msg = timeline_df.loc[msg_idx]

    col_left, col_right = st.columns([2, 1])
    with col_left:
        st.markdown("**Content:**")
        content = msg.get("message_content", "")
        if content and str(content) != "nan":
            st.code(str(content), language=None)
        else:
            st.text("(no content)")

    with col_right:
        st.markdown("**Metadata:**")
        detail_fields = [
            ("UUID", "uuid"),
            ("Parent UUID", "parent_uuid"),
            ("Type", "message_type"),
            ("Role", "message_role"),
            ("Timestamp", "timestamp"),
            ("Model", "model"),
            ("Tool", "tool_name"),
            ("Tool Use ID", "tool_use_id"),
            ("Input Tokens", "input_tokens"),
            ("Output Tokens", "output_tokens"),
            ("Cache Creation", "cache_creation_tokens"),
            ("Cache Read", "cache_read_tokens"),
            ("Stop Reason", "stop_reason"),
        ]
        for label, col in detail_fields:
            val = msg.get(col)
            if val is not None and str(val) != "nan" and str(val) != "None":
                st.text(f"{label}: {val}")
