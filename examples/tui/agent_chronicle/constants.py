"""Constants shared across the Agent Chronicle TUI."""

# Badge colors: (foreground, background) per message type
BADGE_COLORS: dict[str, tuple[str, str]] = {
    "user":               ("#a3e635", "#1a2e05"),
    "assistant":          ("#fbbf24", "#451a03"),
    "system":             ("#64748b", "#1e293b"),
    "summary":            ("#64748b", "#1e293b"),
    "tool_start":         ("#22d3ee", "#083344"),
    "tool_result":        ("#22d3ee", "#083344"),
    "session_start":      ("#e879f9", "#3b0764"),
    "session_resume":     ("#e879f9", "#3b0764"),
    "session_info":       ("#38bdf8", "#0c4a6e"),
    "session_error":      ("#ef4444", "#450a0a"),
    "turn_start":         ("#94a3b8", "#1e293b"),
    "turn_end":           ("#94a3b8", "#1e293b"),
    "reasoning":          ("#a78bfa", "#2e1065"),
    "truncation":         ("#fbbf24", "#451a03"),
    "model_change":       ("#f97316", "#431407"),
    "compaction_start":   ("#fbbf24", "#451a03"),
    "compaction_complete": ("#fbbf24", "#451a03"),
    "abort":              ("#ef4444", "#450a0a"),
}

DEFAULT_BADGE_COLORS = ("#94a3b8", "#1e293b")

# Sample queries for SQL screen (templates with {FROM} placeholder)
SAMPLE_QUERIES: dict[str, dict[str, str]] = {
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
        "Message types": """SELECT source, message_type, COUNT(*) AS count
FROM {FROM}
WHERE message_type != '_parse_error'
GROUP BY source, message_type
ORDER BY source, count DESC""",
        "Longest sessions": """SELECT source, session_id, project_path,
       COUNT(*) AS messages,
       SUM(COALESCE(input_tokens, 0)) AS total_input_tokens
FROM {FROM}
WHERE message_type != '_parse_error'
GROUP BY source, session_id, project_path
ORDER BY messages DESC
LIMIT 10""",
    },
    "📝 Todos & Plans": {
        "Active todos": """SELECT source, session_id, content, status
FROM {TODOS_FROM}
ORDER BY item_index""",
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
}

# Column maps for query builder
COLUMN_MAP: dict[str, list[str]] = {
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
