"""Session Browser screen — filterable table + event timeline + detail panel."""

from __future__ import annotations

import json
from datetime import datetime

import pandas as pd
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Static, DataTable, Input, Button
from textual.worker import WorkerState
from textual import work

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
    fg, _ = BADGE_COLORS.get(msg_type, DEFAULT_BADGE_COLORS)
    return f"[{fg}][{msg_type}][/{fg}]"


# ── Session Browser Screen ──────────────────────────────────────────────


class BrowserScreen(Static):
    """Session Browser with table, timeline, and detail panel."""

    DEFAULT_CSS = """
    BrowserScreen {
        height: 1fr;
    }
    #browser-title {
        text-style: bold;
        color: $primary;
        padding: 0 0 1 0;
    }
    #table-view {
        height: 1fr;
    }
    #filter-row {
        height: 3;
        margin: 0 0 0 0;
    }
    #filter-input {
        width: 1fr;
    }
    #session-table {
        height: 1fr;
    }
    #session-count {
        color: $foreground 60%;
        height: 1;
    }
    #timeline-view {
        height: 1fr;
    }
    #timeline-container {
        height: 1fr;
    }
    #event-list {
        width: 2fr;
        height: 1fr;
    }
    #detail-panel {
        width: 3fr;
        height: 1fr;
        overflow-y: auto;
        padding: 0 1;
        background: $surface;
        border-left: tall $surface;
    }
    #back-button {
        margin: 0 0 0 0;
        dock: top;
    }
    #session-meta {
        color: $foreground 60%;
        height: 1;
    }
    #stats-bar {
        color: $foreground 40%;
        height: 1;
    }
    """

    BINDINGS = [
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("l", "open_selection", "Open", show=False),
        Binding("h", "go_back", "Back", show=False),
        Binding("escape", "go_back", "Back", show=False),
        Binding("enter", "open_selection", "Open", show=False),
        Binding("slash", "focus_filter", "Filter", show=False),
    ]

    def __init__(self, claude_path: str, copilot_path: str, **kwargs):
        super().__init__(**kwargs)
        self.claude_path = claude_path
        self.copilot_path = copilot_path
        self._sessions_df: pd.DataFrame = pd.DataFrame()
        self._filtered_df: pd.DataFrame = pd.DataFrame()
        self._events_df: pd.DataFrame = pd.DataFrame()
        self._selected_path: str | None = None
        self._selected_session_id: str | None = None
        self._view = "table"  # "table" or "timeline"

    def compose(self) -> ComposeResult:
        yield Static("📋 Session Browser", id="browser-title")
        # Table view
        with Vertical(id="table-view"):
            with Horizontal(id="filter-row"):
                yield Input(placeholder="Filter sessions… (press /)", id="filter-input")
            yield Static("Loading sessions…", id="session-count")
            yield DataTable(id="session-table")
        # Timeline view (hidden initially)
        with Vertical(id="timeline-view"):
            yield Button("← Back  [h]", id="back-button", variant="default")
            yield Static("", id="session-meta")
            yield Static("", id="stats-bar")
            with Horizontal(id="timeline-container"):
                yield DataTable(id="event-list")
                yield Static("[dim #6c7086]← Select an event to see details[/dim #6c7086]", id="detail-panel")

    def on_mount(self) -> None:
        self._show_table_view()
        self._load_sessions_async()

    @work(thread=True, exclusive=True, name="load_sessions")
    def _load_sessions_async(self) -> pd.DataFrame:
        """Load session index from both sources in a background thread."""
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
            return pd.concat(all_dfs, ignore_index=True).sort_values(
                "first_ts", ascending=False
            )
        return pd.DataFrame()

    def on_worker_state_changed(self, event) -> None:
        if event.state == WorkerState.SUCCESS and event.worker.name == "load_sessions":
            self._on_sessions_loaded(event.worker.result if event.worker.result is not None else pd.DataFrame())

    def _on_sessions_loaded(self, sessions_df: pd.DataFrame) -> None:
        """Called on main thread when session data is ready."""
        self._sessions_df = sessions_df
        self._apply_filter("")

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
            self.query_one("#event-list", DataTable).focus()
        except Exception:
            pass

    def _apply_filter(self, search: str) -> None:
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
            count_widget.update(f"[#a6adc8]{len(self._filtered_df)} sessions[/#a6adc8]")
        except Exception:
            pass

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "filter-input":
            self._apply_filter(event.value)

    # ── Vim-style actions ───────────────────────────────────────

    def action_cursor_down(self) -> None:
        table = self._active_table()
        if table:
            table.action_cursor_down()

    def action_cursor_up(self) -> None:
        table = self._active_table()
        if table:
            table.action_cursor_up()

    def action_open_selection(self) -> None:
        if self._view == "table":
            self._open_highlighted_session()
        else:
            self._show_highlighted_event()

    def action_go_back(self) -> None:
        if self._view == "timeline":
            self._show_table_view()
            try:
                self.query_one("#session-table", DataTable).focus()
            except Exception:
                pass

    def action_focus_filter(self) -> None:
        try:
            self.query_one("#filter-input", Input).focus()
        except Exception:
            pass

    def _active_table(self) -> DataTable | None:
        tid = "session-table" if self._view == "table" else "event-list"
        try:
            return self.query_one(f"#{tid}", DataTable)
        except Exception:
            return None

    def _open_highlighted_session(self) -> None:
        try:
            table = self.query_one("#session-table", DataTable)
            row_idx = table.cursor_row
        except Exception:
            return
        if row_idx < len(self._filtered_df):
            sel = self._filtered_df.iloc[row_idx]
            self._selected_path = sel["_path"]
            self._selected_session_id = sel["session_id"]
            self._load_timeline()
            self._show_timeline_view()

    def _show_highlighted_event(self) -> None:
        try:
            table = self.query_one("#event-list", DataTable)
            row_idx = table.cursor_row
        except Exception:
            return
        if row_idx < len(self._events_df):
            self._show_event_detail(row_idx)

    # Show event detail on cursor move (single-click / arrow key)
    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id == "event-list" and not self._events_df.empty:
            row_idx = event.cursor_row
            if row_idx < len(self._events_df):
                self._show_event_detail(row_idx)

    # Enter/double-click on session table opens timeline
    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id == "session-table":
            self._open_highlighted_session()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-button":
            self._show_table_view()

    def _load_timeline(self) -> None:
        if not self._selected_path or not self._selected_session_id:
            return

        self._events_df = load_session_events(self._selected_path, self._selected_session_id)

        if self._events_df.empty:
            return

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

        try:
            dur = (last_ts - first_ts).total_seconds() * 1000 if first_ts and last_ts else 0
            meta_text = f"[bold]Session:[/bold] {self._selected_session_id[:16]}… │ [bold]Events:[/bold] {len(self._events_df)} │ [bold]Duration:[/bold] {format_duration(dur)}"
            self.query_one("#session-meta", Static).update(meta_text)
            self.query_one("#stats-bar", Static).update(
                f"[dim]{len(self._events_df)} events │ {format_duration(dur)}[/dim]"
            )
        except Exception:
            pass

        self._populate_event_list()

    def _populate_event_list(self) -> None:
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
        if idx >= len(self._events_df):
            return

        event = self._events_df.iloc[idx]
        msg_type = str(event.get("message_type", ""))
        content = str(event.get("message_content", "") or "")
        tool = str(event.get("tool_name", "") or "")
        tool_input = str(event.get("tool_input", "") or "")

        lines = []
        fg, _ = BADGE_COLORS.get(msg_type, DEFAULT_BADGE_COLORS)
        lines.append(f"[bold {fg}]▎ {msg_type.upper()}[/bold {fg}]")
        lines.append("")

        if msg_type == "user":
            lines.append("[bold #89b4fa]USER MESSAGE[/bold #89b4fa]")
            lines.append(content[:2000] if content else "(empty)")
        elif msg_type == "assistant":
            if tool:
                lines.append(f"[bold #89b4fa]TOOL CALL[/bold #89b4fa]: {tool}")
                if tool_input and tool_input not in ("None", ""):
                    try:
                        parsed = json.loads(tool_input)
                        lines.append(json.dumps(parsed, indent=2)[:1000])
                    except (json.JSONDecodeError, TypeError):
                        lines.append(tool_input[:500])
            elif content:
                lines.append("[bold #89b4fa]RESPONSE[/bold #89b4fa]")
                lines.append(content[:2000])
        elif msg_type in ("tool_start", "tool_result"):
            label = "TOOL EXECUTION" if msg_type == "tool_start" else "TOOL RESULT"
            lines.append(f"[bold #89b4fa]{label}[/bold #89b4fa]: {tool}")
            if content:
                lines.append(content[:1000])
        else:
            lines.append(f"[bold #89b4fa]{msg_type.upper()}[/bold #89b4fa]")
            if content:
                lines.append(content[:1000])

        lines.append("")
        lines.append("[bold #6c7086]─── METADATA ───[/bold #6c7086]")
        for label, col in [
            ("Timestamp", "timestamp"), ("Model", "model"),
            ("Tool", "tool_name"), ("Input Tokens", "input_tokens"),
            ("Output Tokens", "output_tokens"), ("UUID", "uuid"),
        ]:
            val = event.get(col)
            if _is_valid(val) and str(val) not in ("nan", "None", "", "<NA>"):
                lines.append(f"  [#a6adc8]{label}:[/#a6adc8] {val}")

        try:
            panel = self.query_one("#detail-panel", Static)
            panel.update("\n".join(lines))
        except Exception:
            pass
