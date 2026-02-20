"""SQL Query screen — interactive editor with results table."""

from __future__ import annotations

import time

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static, DataTable, TextArea, Button, Select

from agent_chronicle.db import run_query, path_expr
from agent_chronicle.constants import SAMPLE_QUERIES, COLUMN_MAP


class SQLScreen(Static):
    """SQL Query editor with execution and results display."""

    DEFAULT_CSS = """
    SQLScreen {
        height: auto;
    }
    #sql-title {
        text-style: bold;
        color: #a3e635;
        padding: 0 0 1 0;
    }
    #sql-toolbar {
        height: 3;
        margin: 0 0 1 0;
    }
    #sql-source-select {
        width: 20;
    }
    #sql-table-select {
        width: 30;
    }
    #sql-editor {
        height: 10;
        margin: 0 0 1 0;
    }
    #sql-buttons {
        height: 3;
        margin: 0 0 1 0;
    }
    #sql-run-btn {
        margin: 0 1 0 0;
    }
    #sql-samples-btn {
        margin: 0 1 0 0;
    }
    #sql-status {
        color: #94a3b8;
        padding: 0 0 1 0;
    }
    #sql-results {
        height: 16;
        margin: 0;
    }
    #samples-panel {
        background: #1e293b;
        border: tall #334155;
        padding: 1 2;
        margin: 0 0 1 0;
        height: auto;
        max-height: 20;
        display: none;
    }
    .sample-category {
        color: #a3e635;
        text-style: bold;
        padding: 1 0 0 0;
    }
    """

    def __init__(self, claude_path: str, copilot_path: str, **kwargs):
        super().__init__(**kwargs)
        self.claude_path = claude_path
        self.copilot_path = copilot_path
        self._source = "claude"
        self._show_samples = False

    def compose(self) -> ComposeResult:
        yield Static("🔎 SQL Query", id="sql-title")
        with Horizontal(id="sql-toolbar"):
            yield Select(
                [("Claude", "claude"), ("Copilot", "copilot"), ("Both", "both")],
                value="claude",
                id="sql-source-select",
                allow_blank=False,
            )
        yield TextArea(
            "SELECT * FROM read_conversations() LIMIT 10",
            language="sql",
            id="sql-editor",
        )
        with Horizontal(id="sql-buttons"):
            yield Button("▶ Run (F5)", id="sql-run-btn", variant="primary")
            yield Button("📋 Samples", id="sql-samples-btn", variant="default")
        yield Static("", id="sql-status")
        yield Static("", id="samples-panel")
        yield DataTable(id="sql-results")

    def on_mount(self) -> None:
        table = self.query_one("#sql-results", DataTable)
        table.cursor_type = "row"

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "sql-source-select":
            self._source = str(event.value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "sql-run-btn":
            self._execute_query()
        elif event.button.id == "sql-samples-btn":
            self._toggle_samples()
        elif hasattr(event.button, "id") and event.button.id and event.button.id.startswith("sample-"):
            self._load_sample(event.button.id)

    def on_key(self, event) -> None:
        if event.key == "f5":
            self._execute_query()

    def _execute_query(self) -> None:
        """Run the SQL query and display results."""
        try:
            editor = self.query_one("#sql-editor", TextArea)
            sql = editor.text.strip()
        except Exception:
            return

        if not sql:
            self._set_status("⚠️ No query to execute")
            return

        self._set_status("⏳ Executing…")
        start = time.time()

        try:
            df = run_query(sql)
            elapsed = time.time() - start
            self._set_status(f"✅ {len(df)} rows returned ({elapsed:.2f}s)")
            self._display_results(df)
        except Exception as e:
            elapsed = time.time() - start
            self._set_status(f"❌ Error ({elapsed:.2f}s): {e}")

    def _display_results(self, df) -> None:
        """Show query results in the DataTable."""
        try:
            table = self.query_one("#sql-results", DataTable)
        except Exception:
            return

        table.clear(columns=True)

        if df.empty:
            return

        # Add columns
        for col in df.columns:
            table.add_column(str(col))

        # Add rows (limit to 500 for performance)
        for _, row in df.head(500).iterrows():
            table.add_row(*[str(v)[:100] for v in row.values])

    def _set_status(self, text: str) -> None:
        try:
            self.query_one("#sql-status", Static).update(text)
        except Exception:
            pass

    def _toggle_samples(self) -> None:
        """Toggle sample queries panel."""
        self._show_samples = not self._show_samples
        try:
            panel = self.query_one("#samples-panel", Static)
            if self._show_samples:
                lines = []
                for category, queries in SAMPLE_QUERIES.items():
                    lines.append(f"\n[bold #a3e635]{category}[/bold #a3e635]")
                    for name, template in queries.items():
                        lines.append(f"  • {name}")
                panel.update("\n".join(lines))
                panel.display = True
            else:
                panel.display = False
        except Exception:
            pass

    def _load_sample(self, button_id: str) -> None:
        """Load a sample query into the editor."""
        # Decode category and query name from button id
        pass

    def load_sample_query(self, template: str) -> None:
        """Load a sample query template into the editor."""
        rendered = self._render_query(template)
        try:
            editor = self.query_one("#sql-editor", TextArea)
            editor.text = rendered
        except Exception:
            pass

    def _render_query(self, template: str) -> str:
        """Replace template placeholders with actual path expressions."""
        return (
            template
            .replace("{FROM}", path_expr(self._source, "read_conversations", self.claude_path, self.copilot_path))
            .replace("{STATS_FROM}", path_expr(self._source, "read_stats", self.claude_path, self.copilot_path))
            .replace("{TODOS_FROM}", path_expr(self._source, "read_todos", self.claude_path, self.copilot_path))
            .replace("{PLANS_FROM}", path_expr(self._source, "read_plans", self.claude_path, self.copilot_path))
            .replace("{HISTORY_FROM}", path_expr(self._source, "read_history", self.claude_path, self.copilot_path))
        )
