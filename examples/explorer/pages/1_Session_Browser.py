"""Session Browser — Chronicle-style session explorer.

Two-phase browsing: pick a session, then explore its event timeline
with filters, color-coded badges, time deltas, and a detail panel.
"""

import streamlit as st
import pandas as pd
import json
import sys, os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import get_connection, get_data_paths, load_session_index, load_session_events

st.set_page_config(page_title="Session Browser", page_icon="📋", layout="wide")

con = get_connection()
claude_path, copilot_path = get_data_paths()

# ── colour helpers ──────────────────────────────────────────────────────────
BADGE_COLORS = {
    "user":      ("#e879f9", "#1a0820"),   # purple
    "assistant": ("#f97316", "#1c0f00"),   # orange
    "system":    ("#64748b", "#0f172a"),   # slate
    "summary":   ("#64748b", "#0f172a"),
    "tool_start":  ("#22d3ee", "#042f2e"), # cyan
    "tool_result": ("#22d3ee", "#042f2e"),
    "session_start":  ("#a3e635", "#1a2e05"), # lime
    "session_resume": ("#a3e635", "#1a2e05"),
    "session_info":   ("#38bdf8", "#0c1929"), # sky
    "session_error":  ("#ef4444", "#2d0a0a"), # red
    "turn_start":  ("#94a3b8", "#1e293b"), # gray
    "turn_end":    ("#94a3b8", "#1e293b"),
    "reasoning":   ("#a78bfa", "#1e1040"), # violet
    "truncation":  ("#fbbf24", "#1c1a05"), # amber
    "model_change": ("#fbbf24", "#1c1a05"),
    "compaction_start":    ("#fbbf24", "#1c1a05"),
    "compaction_complete": ("#fbbf24", "#1c1a05"),
    "abort": ("#ef4444", "#2d0a0a"),
}

def badge_html(msg_type: str) -> str:
    fg, bg = BADGE_COLORS.get(msg_type, ("#94a3b8", "#1e293b"))
    return (
        f'<span style="display:inline-block;padding:2px 8px;border-radius:4px;'
        f'font-size:12px;font-family:monospace;font-weight:600;'
        f'color:{fg};background:{bg};border:1px solid {fg}40;">'
        f'{msg_type}</span>'
    )


def format_delta_ms(ms: float) -> str:
    if not ms or ms < 0:
        return ""
    abs_ms = abs(ms)
    if abs_ms < 1000:
        return f"+{int(abs_ms)}ms"
    if abs_ms < 60_000:
        return f"+{abs_ms/1000:.1f}s"
    m = int(abs_ms // 60_000)
    s = int((abs_ms % 60_000) // 1000)
    return f"+{m}m {s:02d}s"


def format_duration(ms: float) -> str:
    if not ms or ms <= 0:
        return ""
    abs_ms = abs(ms)
    if abs_ms < 60_000:
        return f"{abs_ms/1000:.1f}s"
    if abs_ms < 3_600_000:
        m = int(abs_ms // 60_000)
        s = int((abs_ms % 60_000) // 1000)
        return f"{m}m {s:02d}s"
    h = int(abs_ms // 3_600_000)
    m = int((abs_ms % 3_600_000) // 60_000)
    return f"{h}h {m}m"


def summarize_event(row: pd.Series) -> str:
    """Create a one-line summary of an event, similar to Chronicle."""
    msg_type = row.get("message_type", "")
    content = str(row.get("message_content", "") or "")
    tool = str(row.get("tool_name", "") or "")
    role = str(row.get("message_role", "") or "")

    max_len = 200

    if msg_type == "user":
        text = content.replace("\n", " ").strip()
        prefix = "User: " if role == "user" else ""
        full = f"{prefix}{text}"
        return full[:max_len] + "…" if len(full) > max_len else full

    if msg_type == "assistant":
        if tool:
            # Tool call from assistant
            return f"Assistant calls: {tool}"
        text = content.replace("\n", " ").strip()
        full = f"Assistant: {text}" if text else "Assistant: (no content)"
        return full[:max_len] + "…" if len(full) > max_len else full

    if msg_type in ("tool_start", "tool_result"):
        tool_input = str(row.get("tool_input", "") or "")
        if msg_type == "tool_start":
            # Show truncated arguments
            args_preview = ""
            if tool_input and tool_input != "None":
                try:
                    args = json.loads(tool_input)
                    args_preview = ", ".join(f"{k}=…" for k in list(args.keys())[:2])
                except (json.JSONDecodeError, TypeError):
                    args_preview = "…"
            return f"⚡ {tool}({args_preview})"
        else:
            return f"✓ {tool} completed"

    if msg_type == "session_start":
        version = row.get("version", "")
        return f"Session started — v{version}" if version else "Session started"

    if msg_type == "session_info":
        text = content.replace("\n", " ").strip()
        return text[:max_len] + "…" if len(text) > max_len else text

    if msg_type == "session_error":
        text = content.replace("\n", " ").strip()
        return f"Error: {text[:max_len]}"

    if msg_type == "turn_start":
        return "Turn started"

    if msg_type == "turn_end":
        return "Turn ended"

    if msg_type == "truncation":
        tokens = row.get("input_tokens", "")
        return f"Truncation: {tokens} tokens removed" if tokens else "Truncation"

    if msg_type == "reasoning":
        text = content.replace("\n", " ").strip()
        full = f"Reasoning: {text}"
        return full[:max_len] + "…" if len(full) > max_len else full

    if msg_type == "system":
        text = content.replace("\n", " ").strip()
        return f"System: {text[:max_len]}"

    if msg_type == "summary":
        return "Conversation summary"

    # Generic fallback
    text = content.replace("\n", " ").strip() if content else msg_type
    return text[:max_len] + "…" if len(text) > max_len else text


def parse_ts(ts_str) -> datetime | None:
    if not ts_str or str(ts_str) == "nan" or str(ts_str) == "None":
        return None
    try:
        s = str(ts_str).strip()
        # Handle ISO 8601 with various suffixes
        for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ",
                     "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S",
                     "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
        return pd.to_datetime(s).to_pydatetime()
    except Exception:
        return None


# ── CSS for Chronicle-like dark theme ───────────────────────────────────────
st.markdown("""
<style>
/* Event row styling */
.event-row {
    display: grid;
    grid-template-columns: 140px 1fr;
    gap: 12px;
    padding: 10px 16px;
    border-bottom: 1px solid #1e293b;
    cursor: pointer;
    transition: background 0.15s;
}
.event-row:hover {
    background: #1e293b;
}
.event-row.selected {
    background: #1e3a5f;
    border-left: 3px solid #3b82f6;
}
.event-time {
    font-family: 'SF Mono', 'Fira Code', monospace;
    font-size: 12px;
    line-height: 1.4;
    color: #e2e8f0;
}
.event-time .delta {
    color: #64748b;
    font-size: 11px;
}
.event-time .offset {
    color: #475569;
    font-size: 11px;
}
.event-summary {
    font-size: 14px;
    line-height: 1.5;
    color: #cbd5e1;
    word-break: break-word;
}
.detail-label {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #64748b;
    margin-bottom: 4px;
}
.detail-content {
    font-size: 14px;
    line-height: 1.6;
    white-space: pre-wrap;
    word-break: break-word;
}
.stats-bar {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    padding: 8px 16px;
    font-size: 13px;
    border-bottom: 1px solid #1e293b;
    color: #94a3b8;
}
.stats-bar strong {
    color: #e2e8f0;
}
.day-sep {
    padding: 6px 16px;
    font-size: 12px;
    font-weight: 600;
    color: #64748b;
    background: #0f172a;
    border-bottom: 1px solid #1e293b;
}
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════
# PHASE 1: Source & session selection
# ═══════════════════════════════════════════════════════════════════════════

st.sidebar.header("📋 Session Browser")

# Source selection
source_choice = st.sidebar.radio(
    "Data source",
    ["Claude (~/.claude)", "Copilot (~/.copilot)", "Both"],
    index=0,
)

paths_to_load = []
if source_choice == "Claude (~/.claude)" or source_choice == "Both":
    paths_to_load.append(claude_path)
if source_choice == "Copilot (~/.copilot)" or source_choice == "Both":
    paths_to_load.append(copilot_path)

# Load session index
all_sessions = []
for p in paths_to_load:
    df = load_session_index(p)
    if not df.empty:
        df["_path"] = p
        all_sessions.append(df)

if not all_sessions:
    st.warning("No sessions found. Check your data paths.")
    st.info(f"Claude: `{claude_path}` | Copilot: `{copilot_path}`")
    st.stop()

sessions_df = pd.concat(all_sessions, ignore_index=True).sort_values("first_ts", ascending=False)

# ── Sidebar: filter sessions ────────────────────────────────────────────
st.sidebar.divider()
st.sidebar.subheader("Filter Sessions")

projects = sorted(sessions_df["project_path"].dropna().unique())
if projects:
    selected_project = st.sidebar.selectbox("Project", ["All"] + projects)
    if selected_project != "All":
        sessions_df = sessions_df[sessions_df["project_path"] == selected_project]

min_events = st.sidebar.slider("Min events", 0, max(int(sessions_df["event_count"].max()), 1), 0)
if min_events > 0:
    sessions_df = sessions_df[sessions_df["event_count"] >= min_events]

# ── Session picker ──────────────────────────────────────────────────────
st.sidebar.divider()
st.sidebar.subheader(f"Sessions ({len(sessions_df)})")

session_labels = []
session_map = {}
for _, row in sessions_df.iterrows():
    proj = row["project_path"] or "unknown"
    proj_short = proj.split("/")[-1] if "/" in str(proj) else proj
    ts = str(row["first_ts"])[:16] if row["first_ts"] else "?"
    label = f"{proj_short} — {row['event_count']} events — {ts}"
    session_labels.append(label)
    session_map[label] = (row["session_id"], row["_path"], row["source"])

if not session_labels:
    st.info("No sessions match filters.")
    st.stop()

selected_session_label = st.sidebar.radio(
    "Pick a session",
    session_labels,
    label_visibility="collapsed",
)

session_id, source_path, session_source = session_map[selected_session_label]

# ═══════════════════════════════════════════════════════════════════════════
# PHASE 2: Session timeline (Chronicle-style)
# ═══════════════════════════════════════════════════════════════════════════

events_df = load_session_events(source_path, session_id)

if events_df.empty:
    st.warning("No events found for this session.")
    st.stop()

# Parse timestamps
events_df["_ts"] = events_df["timestamp"].apply(parse_ts)

# Calculate deltas
deltas_ms = []
first_ts = events_df["_ts"].dropna().iloc[0] if events_df["_ts"].notna().any() else None
for i, row in events_df.iterrows():
    ts = row["_ts"]
    if ts is None or first_ts is None:
        deltas_ms.append(None)
        continue
    if i == events_df.index[0]:
        deltas_ms.append(0)
    else:
        prev_ts = events_df.loc[events_df.index[events_df.index.get_loc(i) - 1], "_ts"]
        if prev_ts:
            deltas_ms.append((ts - prev_ts).total_seconds() * 1000)
        else:
            deltas_ms.append(None)

events_df["_delta_ms"] = deltas_ms
events_df["_offset_ms"] = events_df["_ts"].apply(
    lambda t: (t - first_ts).total_seconds() * 1000 if t and first_ts else None
)

# ── Top filter bar (Chronicle-style) ────────────────────────────────────
st.markdown("### Session Timeline")

filter_cols = st.columns([2, 3, 2, 2, 1])

with filter_cols[0]:
    search_query = st.text_input("🔍 Search", "", placeholder="message, tool name…",
                                  label_visibility="collapsed")

all_types = sorted(events_df["message_type"].dropna().unique())
with filter_cols[1]:
    type_filter = st.selectbox("Type", ["All"] + all_types, label_visibility="collapsed")

with filter_cols[2]:
    hide_noise = st.checkbox("Hide turn/truncation", value=False)

with filter_cols[3]:
    truncate_content = st.checkbox("Truncate long strings", value=True)

with filter_cols[4]:
    if st.button("Clear"):
        # Rerun to reset
        st.rerun()

# Apply filters
filtered_df = events_df.copy()
if type_filter != "All":
    filtered_df = filtered_df[filtered_df["message_type"] == type_filter]
if hide_noise:
    noise_types = {"turn_start", "turn_end", "truncation", "compaction_start", "compaction_complete"}
    filtered_df = filtered_df[~filtered_df["message_type"].isin(noise_types)]
if search_query:
    q = search_query.lower()
    mask = (
        filtered_df["message_content"].fillna("").str.lower().str.contains(q, na=False) |
        filtered_df["tool_name"].fillna("").str.lower().str.contains(q, na=False) |
        filtered_df["message_type"].fillna("").str.lower().str.contains(q, na=False)
    )
    filtered_df = filtered_df[mask]

# ── Stats bar ───────────────────────────────────────────────────────────
last_ts = events_df["_ts"].dropna().iloc[-1] if events_df["_ts"].notna().any() else None
duration_ms = (last_ts - first_ts).total_seconds() * 1000 if first_ts and last_ts else 0

st.markdown(
    f'<div class="stats-bar">'
    f'<span><strong>{len(filtered_df)}</strong> showing / <strong>{len(events_df)}</strong> events</span>'
    f'<span>Duration: {format_duration(duration_ms)}</span>'
    f'</div>',
    unsafe_allow_html=True,
)

# ── Two-column layout: event list + detail panel ────────────────────────
col_list, col_detail = st.columns([3, 2])

# Use session state to track selected event
if "selected_event_idx" not in st.session_state:
    st.session_state["selected_event_idx"] = None

with col_list:
    # Group events by day
    current_day = None
    for idx, row in filtered_df.iterrows():
        ts = row["_ts"]
        if ts:
            day = ts.strftime("%Y-%m-%d")
            if day != current_day:
                current_day = day
                st.markdown(f'<div class="day-sep">{day}</div>', unsafe_allow_html=True)

        # Build event row
        ts_str = ts.strftime("%H:%M:%S.%f")[:-3] if ts else "—"
        delta_str = format_delta_ms(row.get("_delta_ms")) if row.get("_delta_ms") else ""
        offset_str = f"t{format_delta_ms(row.get('_offset_ms'))}" if row.get("_offset_ms") else ""
        badge = badge_html(row["message_type"])
        summary = summarize_event(row)

        # Clicking a button selects the event
        btn_key = f"evt_{idx}"
        is_selected = st.session_state.get("selected_event_idx") == idx

        container = st.container()
        with container:
            c1, c2 = st.columns([1, 4])
            with c1:
                st.markdown(
                    f'<div class="event-time">'
                    f'<div>{ts_str}</div>'
                    f'<div class="delta">{delta_str}</div>'
                    f'<div class="offset">{offset_str}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            with c2:
                st.markdown(f'{badge}', unsafe_allow_html=True)
                if st.button(summary[:120], key=btn_key, use_container_width=True,
                             type="primary" if is_selected else "secondary"):
                    st.session_state["selected_event_idx"] = idx
                    st.rerun()


# ── Detail panel (right column) ─────────────────────────────────────────
with col_detail:
    sel_idx = st.session_state.get("selected_event_idx")

    if sel_idx is not None and sel_idx in filtered_df.index:
        event = filtered_df.loc[sel_idx]
        msg_type = event.get("message_type", "")

        st.markdown(f"### {badge_html(msg_type)}", unsafe_allow_html=True)

        # ── Formatted content view ──────────────────────────────────────
        content = str(event.get("message_content", "") or "")
        tool = str(event.get("tool_name", "") or "")
        tool_input_str = str(event.get("tool_input", "") or "")

        if msg_type == "user":
            st.markdown(f'<div class="detail-label">USER MESSAGE</div>', unsafe_allow_html=True)
            display = content[:2000] + "…" if truncate_content and len(content) > 2000 else content
            st.markdown(f'<div class="detail-content">{display}</div>', unsafe_allow_html=True)

        elif msg_type == "assistant":
            if tool:
                st.markdown(f'<div class="detail-label">TOOL CALL</div>', unsafe_allow_html=True)
                st.code(f"{tool}", language=None)
                if tool_input_str and tool_input_str != "None":
                    try:
                        parsed_input = json.loads(tool_input_str)
                        display_input = json.dumps(parsed_input, indent=2)
                        if truncate_content and len(display_input) > 2000:
                            display_input = display_input[:2000] + "\n…[truncated]"
                        st.code(display_input, language="json")
                    except (json.JSONDecodeError, TypeError):
                        st.code(tool_input_str[:500], language=None)
            if content:
                st.markdown(f'<div class="detail-label">RESPONSE</div>', unsafe_allow_html=True)
                display = content[:2000] + "…" if truncate_content and len(content) > 2000 else content
                st.text(display)

        elif msg_type in ("tool_start", "tool_result"):
            label = "TOOL EXECUTION" if msg_type == "tool_start" else "TOOL RESULT"
            st.markdown(f'<div class="detail-label">{label}</div>', unsafe_allow_html=True)
            if tool:
                st.code(tool, language=None)
            if tool_input_str and tool_input_str != "None":
                try:
                    parsed_input = json.loads(tool_input_str)
                    st.code(json.dumps(parsed_input, indent=2)[:2000], language="json")
                except (json.JSONDecodeError, TypeError):
                    st.code(tool_input_str[:500], language=None)
            if content:
                display = content[:2000] + "…" if truncate_content and len(content) > 2000 else content
                st.text(display)

        elif msg_type in ("session_start", "session_info", "session_error", "session_resume"):
            st.markdown(f'<div class="detail-label">SESSION EVENT</div>', unsafe_allow_html=True)
            if content:
                st.text(content[:1000])

        elif msg_type in ("system", "summary", "reasoning"):
            st.markdown(f'<div class="detail-label">{msg_type.upper()}</div>', unsafe_allow_html=True)
            display = content[:2000] + "…" if truncate_content and len(content) > 2000 else content
            st.text(display)

        else:
            if content:
                st.markdown(f'<div class="detail-label">{msg_type.upper()}</div>', unsafe_allow_html=True)
                st.text(content[:1000])

        # ── Metadata ────────────────────────────────────────────────────
        st.divider()
        st.markdown(f'<div class="detail-label">METADATA</div>', unsafe_allow_html=True)
        meta_fields = [
            ("UUID", "uuid"), ("Parent UUID", "parent_uuid"),
            ("Timestamp", "timestamp"), ("Model", "model"),
            ("Tool", "tool_name"), ("Tool Use ID", "tool_use_id"),
            ("Input Tokens", "input_tokens"), ("Output Tokens", "output_tokens"),
            ("Cache Creation", "cache_creation_tokens"), ("Cache Read", "cache_read_tokens"),
            ("Stop Reason", "stop_reason"), ("Git Branch", "git_branch"),
            ("CWD", "cwd"), ("Version", "version"),
        ]
        for label, col_name in meta_fields:
            val = event.get(col_name)
            if val is not None and str(val) not in ("nan", "None", ""):
                st.text(f"{label}: {val}")

        # ── Raw JSON ────────────────────────────────────────────────────
        with st.expander("Raw JSON"):
            raw = {}
            for col_name in event.index:
                if col_name.startswith("_"):
                    continue
                v = event[col_name]
                if v is not None and str(v) not in ("nan", "None"):
                    if col_name == "tool_input" and v:
                        try:
                            raw[col_name] = json.loads(str(v))
                        except (json.JSONDecodeError, TypeError):
                            raw[col_name] = str(v)
                    else:
                        raw[col_name] = str(v) if not isinstance(v, (int, float, bool)) else v
            display_json = json.dumps(raw, indent=2, default=str)
            if truncate_content and len(display_json) > 5000:
                display_json = display_json[:5000] + "\n…[truncated]"
            st.code(display_json, language="json")
    else:
        st.info("← Select an event from the timeline to see details")
