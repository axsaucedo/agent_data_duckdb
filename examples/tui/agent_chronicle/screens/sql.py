"""SQL Query screen — interactive editor with results table and samples browser."""

from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Static, DataTable, Input, Button, Select, TabbedContent, TabPane

from agent_chronicle.db import run_query, path_expr
from agent_chronicle.constants import SAMPLE_QUERIES, COLUMN_MAP


class SQLScreen(Static):
    """SQL Query editor with execution, results, and sample query browser."""

    DEFAULT_CSS = """
    SQLScreen {
        height: 1fr;
    }
    #sql-tabs {
        height: 1fr;
    }
    #sql-toolbar {
        height: 3;
        margin: 0 0 0 0;
    }
    #sql-source-select {
        width: 20;
    }
    #sql-editor {
        width: 1fr;
        margin: 0 0 0 0;
    }
    #sql-buttons {
        height: 3;
        margin: 0 0 0 0;
    }
    #sql-run-btn {
        margin: 0 1 0 0;
    }
    #sql-status {
        color: $foreground 60%;
        height: 1;
    }
    #sql-results {
        height: 1fr;
        min-height: 6;
    }
    #samples-table {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("j", "vim_down", "Down", show=False),
        Binding("k", "vim_up", "Up", show=False),
    ]

    def __init__(self, claude_path: str, copilot_path: str, **kwargs):
        super().__init__(**kwargs)
        self.claude_path = claude_path
        self.copilot_path = copilot_path
        self._source = "claude"
        self._sample_queries: list[tuple[str, str, str]] = []  # (category, name, template)

    def compose(self) -> ComposeResult:
        with TabbedContent(id="sql-tabs"):
            with TabPane("🔎 SQL Query", id="sql-query-tab"):
                with Horizontal(id="sql-toolbar"):
                    yield Select(
                        [("Claude", "claude"), ("Copilot", "copilot"), ("Both", "both")],
                        value="claude",
                        id="sql-source-select",
                        allow_blank=False,
                    )
                yield Input(
                    value="SELECT * FROM read_conversations() LIMIT 10",
                    placeholder="Enter SQL query and press Enter…",
                    id="sql-editor",
                )
                with Horizontal(id="sql-buttons"):
                    yield Button("▶ Run (Enter)", id="sql-run-btn", variant="primary")
                yield Static("", id="sql-status")
                yield DataTable(id="sql-results")
            with TabPane("📋 Samples", id="sql-samples-tab"):
                yield DataTable(id="samples-table")

    def on_mount(self) -> None:
        results = self.query_one("#sql-results", DataTable)
        results.cursor_type = "row"
        self._populate_samples_table()

    def _populate_samples_table(self) -> None:
        """Build the samples DataTable from SAMPLE_QUERIES constants."""
        try:
            table = self.query_one("#samples-table", DataTable)
        except Exception:
            return
        table.cursor_type = "row"
        table.add_columns("Category", "Query Name")
        self._sample_queries = []
        for category, queries in SAMPLE_QUERIES.items():
            for name, template in queries.items():
                self._sample_queries.append((category, name, template))
                table.add_row(category, name)

    # ── Vim navigation ─────────────────────────────────────────

    def action_vim_down(self) -> None:
        focused = self.app.focused
        if isinstance(focused, DataTable):
            focused.action_cursor_down()
        elif isinstance(focused, VerticalScroll):
            focused.scroll_down(animate=False)

    def action_vim_up(self) -> None:
        focused = self.app.focused
        if isinstance(focused, DataTable):
            focused.action_cursor_up()
        elif isinstance(focused, VerticalScroll):
            focused.scroll_up(animate=False)

    # ── Event handlers ─────────────────────────────────────────

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "sql-editor":
            self._execute_query()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "sql-source-select":
            self._source = str(event.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "sql-run-btn":
            self._execute_query()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle Enter on samples table to load query into editor."""
        if event.data_table.id == "samples-table":
            row_idx = event.cursor_row
            if row_idx < len(self._sample_queries):
                _, _, template = self._sample_queries[row_idx]
                self._load_sample(template)

    # ── Internal helpers ───────────────────────────────────────

    def _execute_query(self) -> None:
        try:
            editor = self.query_one("#sql-editor", Input)
            sql = editor.value.strip()
        except Exception:
            return

        if not sql:
            self._set_status("⚠ No query to execute")
            return

        self._set_status("⏳ Executing…")
        start = time.time()

        try:
            df = run_query(sql)
            elapsed = time.time() - start
            self._set_status(f"✓ {len(df)} rows ({elapsed:.2f}s)")
            self._display_results(df)
        except Exception as e:
            elapsed = time.time() - start
            self._set_status(f"✗ Error ({elapsed:.2f}s): {e}")

    def _display_results(self, df) -> None:
        try:
            table = self.query_one("#sql-results", DataTable)
        except Exception:
            return

        table.clear(columns=True)

        if df.empty:
            return

        for col in df.columns:
            table.add_column(str(col))

        for _, row in df.head(500).iterrows():
            table.add_row(*[str(v)[:100] for v in row.values])

    def _set_status(self, text: str) -> None:
        try:
            self.query_one("#sql-status", Static).update(text)
        except Exception:
            pass

    def _load_sample(self, template: str) -> None:
        """Load a sample query into the editor and switch to Query tab."""
        rendered = self._render_query(template)
        try:
            editor = self.query_one("#sql-editor", Input)
            editor.value = rendered
            # Switch to Query tab
            self.query_one("#sql-tabs", TabbedContent).active = "sql-query-tab"
            editor.focus()
        except Exception:
            pass

    def _render_query(self, template: str) -> str:
        return (
            template
            .replace("{FROM}", path_expr(self._source, "read_conversations", self.claude_path, self.copilot_path))
            .replace("{STATS_FROM}", path_expr(self._source, "read_stats", self.claude_path, self.copilot_path))
            .replace("{TODOS_FROM}", path_expr(self._source, "read_todos", self.claude_path, self.copilot_path))
            .replace("{PLANS_FROM}", path_expr(self._source, "read_plans", self.claude_path, self.copilot_path))
            .replace("{HISTORY_FROM}", path_expr(self._source, "read_history", self.claude_path, self.copilot_path))
        )
