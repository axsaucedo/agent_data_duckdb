"""Session Browser screen — filterable table + event timeline + detail panel."""

from __future__ import annotations

import json
from datetime import datetime

import pandas as pd
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Static, DataTable, Input, Button, Label
from textual.widget import Widget

from agent_chronicle.db import load_session_index, load_session_events
from agent_chronicle.constants import BADGE_COLORS, DEFAULT_BADGE_COLORS


# ── Helpers (ported from Streamlit explorer) ────────────────────────────


def _is_valid(val) -> bool:
    if val is None:
        return False
    try:
        if pd.isna(val):
            return False
    except (TypeError, ValueError):
        pass
    return True


def parse_ts(ts_str) -> datetime | None:
    if not _is_valid(ts_str):
        return None
    s = str(ts_str).strip()
    if not s or s in ("nan", "None", "NaT", ""):
        return None
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z",
    ):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    try:
        result = pd.to_datetime(s)
        if pd.isna(result):
            return None
        return result.to_pydatetime()
    except Exception:
        return None


def format_delta(ms) -> str:
    if not _is_valid(ms) or ms <= 0:
        return ""
    if ms < 1000:
        return f"+{int(ms)}ms"
    if ms < 60_000:
        return f"+{ms / 1000:.1f}s"
    m, s = int(ms // 60_000), int((ms % 60_000) // 1000)
    return f"+{m}m {s:02d}s"


def format_duration(ms) -> str:
    if not _is_valid(ms) or ms <= 0:
        return ""
    if ms < 60_000:
        return f"{ms / 1000:.1f}s"
    if ms < 3_600_000:
        m, s = int(ms // 60_000), int((ms % 60_000) // 1000)
        return f"{m}m {s:02d}s"
    h, m = int(ms // 3_600_000), int((ms % 3_600_000) // 60_000)
    return f"{h}h {m}m"


def summarize_event(row: pd.Series, max_len: int = 120) -> str:
    msg_type = str(row.get("message_type", ""))
    content = str(row.get("message_content", "") or "").replace("\n", " ").strip()
    tool = str(row.get("tool_name", "") or "")
    if msg_type == "user":
        text = content if content else "(empty)"
    elif msg_type == "assistant":
        text = f"calls {tool}" if tool else (content if content else "(no content)")
    elif msg_type == "tool_start":
        args = ""
        ti = str(row.get("tool_input", "") or "")
        if ti and ti != "None":
            try:
                args = ", ".join(f"{k}=…" for k in list(json.loads(ti).keys())[:2])
            except Exception:
                args = "…"
        text = f"⚡ {tool}({args})"
    elif msg_type == "tool_result":
        text = f"✓ {tool} completed"
    elif msg_type == "session_start":
        v = row.get("version", "")
        text = f"Session started — v{v}" if _is_valid(v) else "Session started"
    elif msg_type == "session_info":
        text = content or "Session info"
    elif msg_type == "session_error":
        text = content if content else "Error"
    elif msg_type in ("turn_start", "turn_end"):
        text = "Turn started" if msg_type == "turn_start" else "Turn ended"
    elif msg_type == "truncation":
        tokens = row.get("input_tokens", "")
        text = f"Truncation: {tokens} tokens" if _is_valid(tokens) else "Truncation"
    elif msg_type == "reasoning":
        text = content if content else "Reasoning"
    else:
        text = content or msg_type
    return text[:max_len] + "…" if len(text) > max_len else text


def badge_text(msg_type: str) -> str:
    """Return styled badge text for Rich rendering."""
    fg, _ = BADGE_COLORS.get(msg_type, DEFAULT_BADGE_COLORS)
    return f"[{fg}][{msg_type}][/{fg}]"


# ── Session Browser Screen ──────────────────────────────────────────────


class BrowserScreen(Static):
    """Session Browser with table, timeline, and detail panel."""

    DEFAULT_CSS = """
    BrowserScreen {
        height: auto;
    }
    #browser-title {
        text-style: bold;
        color: #a3e635;
        padding: 0 0 1 0;
    }
    #filter-row {
        height: 3;
        margin: 0 0 1 0;
    }
    #filter-input {
        width: 1fr;
    }
    #session-table {
        height: 12;
        margin: 0 0 1 0;
    }
    #session-count {
        color: #94a3b8;
        padding: 0 0 1 0;
    }
    #timeline-container {
        height: auto;
        min-height: 15;
    }
    #event-list {
        width: 2fr;
        height: 24;
        overflow-y: auto;
    }
    #detail-panel {
        width: 3fr;
        height: 24;
        overflow-y: auto;
        padding: 0 1;
    }
    .event-item {
        padding: 0 1;
        margin: 0 0 0 0;
    }
    .event-item:hover {
        background: #334155;
    }
    .day-separator {
        color: #64748b;
        text-style: bold;
        padding: 1 0 0 0;
    }
    #back-button {
        margin: 0 0 1 0;
    }
    #session-meta {
        color: #94a3b8;
        padding: 0 0 1 0;
    }
    #stats-bar {
        color: #94a3b8;
        padding: 0 0 0 0;
    }
    #detail-placeholder {
        color: #64748b;
        padding: 2;
    }
    """

    def __init__(self, claude_path: str, copilot_path: str, **kwargs):
        super().__init__(**kwargs)
        self.claude_path = claude_path
        self.copilot_path = copilot_path
        self._sessions_df: pd.DataFrame = pd.DataFrame()
        self._filtered_df: pd.DataFrame = pd.DataFrame()
        self._events_df: pd.DataFrame = pd.DataFrame()
        self._selected_path: str | None = None
        self._selected_session_id: str | None = None
        self._selected_event_idx: int | None = None
        self._view = "table"  # "table" or "timeline"

    def compose(self) -> ComposeResult:
        yield Static("📋 Session Browser", id="browser-title")
        # Table view
        with Vertical(id="table-view"):
            with Horizontal(id="filter-row"):
                yield Input(placeholder="Filter sessions…", id="filter-input")
            yield Static("", id="session-count")
            yield DataTable(id="session-table")
        # Timeline view (hidden initially)
        with Vertical(id="timeline-view"):
            yield Button("← Back to Sessions", id="back-button", variant="default")
            yield Static("", id="session-meta")
            yield Static("", id="stats-bar")
            with Horizontal(id="timeline-container"):
                yield DataTable(id="event-list")
                yield Static("← Select an event to see details", id="detail-panel")

    def on_mount(self) -> None:
        self._load_sessions()
        self._show_table_view()

    def _show_table_view(self) -> None:
        self._view = "table"
        self._selected_session_id = None
        try:
            self.query_one("#table-view").display = True
            self.query_one("#timeline-view").display = False
        except Exception:
            pass

    def _show_timeline_view(self) -> None:
        self._view = "timeline"
        try:
            self.query_one("#table-view").display = False
            self.query_one("#timeline-view").display = True
        except Exception:
            pass

    def _load_sessions(self) -> None:
        """Load session index from both sources."""
        all_dfs = []
        for path in [self.claude_path, self.copilot_path]:
            try:
                df = load_session_index(path)
                if not df.empty:
                    df["_path"] = path
                    all_dfs.append(df)
            except Exception:
                pass

        if all_dfs:
            self._sessions_df = pd.concat(all_dfs, ignore_index=True).sort_values(
                "first_ts", ascending=False
            )
        else:
            self._sessions_df = pd.DataFrame()

        self._apply_filter("")

    def _apply_filter(self, search: str) -> None:
        """Filter sessions and update the table."""
        df = self._sessions_df.copy()
        if search:
            q = search.lower()
            mask = (
                df["project_path"].fillna("").str.lower().str.contains(q, na=False)
                | df["session_id"].fillna("").str.lower().str.contains(q, na=False)
                | df["first_user_message"].fillna("").str.lower().str.contains(q, na=False)
            )
            df = df[mask]
        self._filtered_df = df
        self._populate_table()

    def _populate_table(self) -> None:
        """Fill the DataTable with session data."""
        try:
            table = self.query_one("#session-table", DataTable)
        except Exception:
            return

        table.clear(columns=True)
        table.add_columns("Source", "Last Active", "Events", "Project", "First Message")
        table.cursor_type = "row"

        for _, row in self._filtered_df.iterrows():
            last = str(row.get("last_ts", ""))[:16] if _is_valid(row.get("last_ts")) else "—"
            events = str(int(row.get("event_count", 0)))
            proj_path = str(row.get("project_path", ""))
            proj = proj_path.split("/")[-1] if "/" in proj_path else proj_path
            first_msg = str(row.get("first_user_message", "")).replace("\n", " ")[:80]
            if not first_msg or first_msg in ("None", "nan"):
                first_msg = "—"
            table.add_row(
                str(row.get("source", "")),
                last,
                events,
                proj if proj else "—",
                first_msg,
            )

        try:
            count_widget = self.query_one("#session-count", Static)
            count_widget.update(f"{len(self._filtered_df)} sessions")
        except Exception:
            pass

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "filter-input":
            self._apply_filter(event.value)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection in session table or event list."""
        table_id = event.data_table.id

        if table_id == "session-table":
            row_idx = event.cursor_row
            if row_idx < len(self._filtered_df):
                sel = self._filtered_df.iloc[row_idx]
                self._selected_path = sel["_path"]
                self._selected_session_id = sel["session_id"]
                self._load_timeline()
                self._show_timeline_view()

        elif table_id == "event-list":
            row_idx = event.cursor_row
            if row_idx < len(self._events_df):
                self._selected_event_idx = row_idx
                self._show_event_detail(row_idx)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-button":
            self._show_table_view()

    def _load_timeline(self) -> None:
        """Load events for the selected session."""
        if not self._selected_path or not self._selected_session_id:
            return

        self._events_df = load_session_events(self._selected_path, self._selected_session_id)

        if self._events_df.empty:
            return

        # Parse timestamps and compute deltas
        self._events_df["_ts"] = self._events_df["timestamp"].apply(parse_ts)

        valid_ts = self._events_df["_ts"].apply(_is_valid)
        first_ts = self._events_df.loc[valid_ts, "_ts"].iloc[0] if valid_ts.any() else None
        last_ts = self._events_df.loc[valid_ts, "_ts"].iloc[-1] if valid_ts.any() else None

        deltas, offsets = [], []
        prev = None
        for _, row in self._events_df.iterrows():
            ts = row["_ts"]
            if _is_valid(ts) and _is_valid(first_ts):
                offsets.append((ts - first_ts).total_seconds() * 1000)
                deltas.append((ts - prev).total_seconds() * 1000 if prev else 0)
                prev = ts
            else:
                deltas.append(None)
                offsets.append(None)

        self._events_df["_delta_ms"] = deltas
        self._events_df["_offset_ms"] = offsets

        # Update session metadata
        try:
            dur = (last_ts - first_ts).total_seconds() * 1000 if first_ts and last_ts else 0
            meta_text = f"Session: {self._selected_session_id[:12]}… | Events: {len(self._events_df)} | Duration: {format_duration(dur)}"
            self.query_one("#session-meta", Static).update(meta_text)
            self.query_one("#stats-bar", Static).update(
                f"{len(self._events_df)} events | Duration: {format_duration(dur)}"
            )
        except Exception:
            pass

        self._populate_event_list()

    def _populate_event_list(self) -> None:
        """Fill the event list DataTable."""
        try:
            table = self.query_one("#event-list", DataTable)
        except Exception:
            return

        table.clear(columns=True)
        table.add_columns("Time", "Type", "Summary")
        table.cursor_type = "row"

        for _, row in self._events_df.iterrows():
            ts = row["_ts"]
            ts_str = ts.strftime("%H:%M:%S") if _is_valid(ts) else "—"
            delta = format_delta(row.get("_delta_ms"))
            msg_type = str(row.get("message_type", ""))
            summary = summarize_event(row, max_len=60)
            time_col = f"{ts_str} {delta}" if delta else ts_str
            table.add_row(time_col, msg_type, summary)

    def _show_event_detail(self, idx: int) -> None:
        """Show event detail in the right panel."""
        if idx >= len(self._events_df):
            return

        event = self._events_df.iloc[idx]
        msg_type = str(event.get("message_type", ""))
        content = str(event.get("message_content", "") or "")
        tool = str(event.get("tool_name", "") or "")
        tool_input = str(event.get("tool_input", "") or "")

        lines = []
        fg, _ = BADGE_COLORS.get(msg_type, DEFAULT_BADGE_COLORS)
        lines.append(f"[bold {fg}][{msg_type}][/bold {fg}]")
        lines.append("")

        # Type-specific rendering
        if msg_type == "user":
            lines.append("[bold]USER MESSAGE[/bold]")
            lines.append(content[:2000] if content else "(empty)")
        elif msg_type == "assistant":
            if tool:
                lines.append(f"[bold]TOOL CALL[/bold]: {tool}")
                if tool_input and tool_input not in ("None", ""):
                    try:
                        parsed = json.loads(tool_input)
                        lines.append(json.dumps(parsed, indent=2)[:1000])
                    except (json.JSONDecodeError, TypeError):
                        lines.append(tool_input[:500])
            elif content:
                lines.append("[bold]RESPONSE[/bold]")
                lines.append(content[:2000])
        elif msg_type in ("tool_start", "tool_result"):
            label = "TOOL EXECUTION" if msg_type == "tool_start" else "TOOL RESULT"
            lines.append(f"[bold]{label}[/bold]: {tool}")
            if content:
                lines.append(content[:1000])
        else:
            lines.append(f"[bold]{msg_type.upper()}[/bold]")
            if content:
                lines.append(content[:1000])

        # Metadata
        lines.append("")
        lines.append("[bold]METADATA[/bold]")
        for label, col in [
            ("Timestamp", "timestamp"), ("Model", "model"),
            ("Tool", "tool_name"), ("Input Tokens", "input_tokens"),
            ("Output Tokens", "output_tokens"), ("UUID", "uuid"),
        ]:
            val = event.get(col)
            if _is_valid(val) and str(val) not in ("nan", "None", "", "<NA>"):
                lines.append(f"  {label}: {val}")

        try:
            panel = self.query_one("#detail-panel", Static)
            panel.update("\n".join(lines))
        except Exception:
            pass
