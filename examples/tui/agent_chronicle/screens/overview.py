"""Overview dashboard screen with metrics and stats."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from agent_chronicle.db import get_connection, union_from, _safe_query


class MetricCard(Static):
    """A single metric card with label and value."""

    DEFAULT_CSS = """
    MetricCard {
        background: #1e293b;
        border: tall #334155;
        padding: 1 2;
        margin: 0 1;
        height: 5;
        width: 1fr;
    }
    """

    def __init__(self, label: str, value: str = "—", **kwargs):
        super().__init__(**kwargs)
        self.label = label
        self.value = value

    def compose(self) -> ComposeResult:
        yield Static(self.value, classes="metric-value")
        yield Static(self.label, classes="metric-label")

    def update_value(self, value: str) -> None:
        self.value = value
        try:
            val_widget = self.query_one(".metric-value", Static)
            val_widget.update(value)
        except Exception:
            pass


class StatsSection(Static):
    """A stats section showing a label and text data."""

    DEFAULT_CSS = """
    StatsSection {
        background: #1e293b;
        border: tall #334155;
        padding: 1 2;
        margin: 1 1;
        height: auto;
        min-height: 5;
    }
    """

    def __init__(self, title: str, content: str = "Loading…", **kwargs):
        super().__init__(**kwargs)
        self._title = title
        self._content = content

    def compose(self) -> ComposeResult:
        yield Static(f"[bold]{self._title}[/bold]", id=f"{self.id}-title" if self.id else None)
        yield Static(self._content, id=f"{self.id}-body" if self.id else None)

    def update_content(self, content: str) -> None:
        self._content = content
        try:
            body = self.query(Static)[-1]
            body.update(content)
        except Exception:
            pass


class OverviewScreen(Static):
    """Overview dashboard with metrics and activity stats."""

    DEFAULT_CSS = """
    OverviewScreen {
        height: auto;
    }
    #overview-title {
        text-style: bold;
        color: #a3e635;
        padding: 0 0 1 0;
    }
    #metrics-row {
        height: 5;
        margin: 0 0 1 0;
    }
    #stats-grid {
        height: auto;
    }
    .stats-row {
        height: auto;
        margin: 0;
    }
    """

    def __init__(self, claude_path: str, copilot_path: str, **kwargs):
        super().__init__(**kwargs)
        self.claude_path = claude_path
        self.copilot_path = copilot_path

    def compose(self) -> ComposeResult:
        yield Static("🤖 Agent Chronicle — Overview", id="overview-title")
        with Horizontal(id="metrics-row"):
            yield MetricCard("Claude Sessions", "—", id="metric-claude-sessions")
            yield MetricCard("Claude Messages", "—", id="metric-claude-messages")
            yield MetricCard("Copilot Sessions", "—", id="metric-copilot-sessions")
            yield MetricCard("Copilot Messages", "—", id="metric-copilot-messages")
        with Vertical(id="stats-grid"):
            with Horizontal(classes="stats-row"):
                yield StatsSection("📊 Messages by Source", "Loading…", id="stats-source")
                yield StatsSection("💬 Message Types (Top 10)", "Loading…", id="stats-types")
            with Horizontal(classes="stats-row"):
                yield StatsSection("📁 Top Projects", "Loading…", id="stats-projects")
                yield StatsSection("🔧 Top Tools", "Loading…", id="stats-tools")
            with Horizontal(classes="stats-row"):
                yield StatsSection("🔢 Token Usage", "Loading…", id="stats-tokens")
                yield StatsSection("📈 Recent Activity", "Loading…", id="stats-activity")

    def on_mount(self) -> None:
        self._load_data_sync()

    def _load_data_sync(self) -> None:
        """Load overview data synchronously (fast with cached queries)."""
        con = get_connection()
        FROM = union_from(self.claude_path, self.copilot_path, "read_conversations")

        # Metrics
        try:
            metrics_df = _safe_query(f"""
                SELECT source,
                       COUNT(DISTINCT session_id) AS sessions,
                       COUNT(*) AS messages
                FROM {FROM} t
                GROUP BY source
            """)
            if not metrics_df.empty:
                claude = metrics_df[metrics_df["source"] == "claude"]
                copilot = metrics_df[metrics_df["source"] == "copilot"]
                self._update_metric("metric-claude-sessions", str(int(claude["sessions"].iloc[0])) if not claude.empty else "0")
                self._update_metric("metric-claude-messages", str(int(claude["messages"].iloc[0])) if not claude.empty else "0")
                self._update_metric("metric-copilot-sessions", str(int(copilot["sessions"].iloc[0])) if not copilot.empty else "0")
                self._update_metric("metric-copilot-messages", str(int(copilot["messages"].iloc[0])) if not copilot.empty else "0")
        except Exception:
            pass

        # Messages by source
        try:
            src_df = _safe_query(f"SELECT source, COUNT(*) AS messages FROM {FROM} t GROUP BY source")
            if not src_df.empty:
                lines = [f"  {r['source']}: {int(r['messages']):,}" for _, r in src_df.iterrows()]
                self._update_stats("stats-source", "\n".join(lines))
        except Exception:
            pass

        # Message types
        try:
            types_df = _safe_query(f"""
                SELECT message_type, COUNT(*) AS count FROM {FROM} t
                WHERE message_type IS NOT NULL
                GROUP BY message_type ORDER BY count DESC LIMIT 10
            """)
            if not types_df.empty:
                lines = [f"  {r['message_type']}: {int(r['count']):,}" for _, r in types_df.iterrows()]
                self._update_stats("stats-types", "\n".join(lines))
        except Exception:
            pass

        # Top projects
        try:
            proj_df = _safe_query(f"""
                SELECT COALESCE(SPLIT_PART(project_path, '/', -1), 'unknown') AS project,
                       COUNT(*) AS messages
                FROM {FROM} t
                WHERE project_path IS NOT NULL AND project_path != ''
                GROUP BY project ORDER BY messages DESC LIMIT 10
            """)
            if not proj_df.empty:
                lines = [f"  {r['project']}: {int(r['messages']):,}" for _, r in proj_df.iterrows()]
                self._update_stats("stats-projects", "\n".join(lines))
        except Exception:
            pass

        # Top tools
        try:
            tools_df = _safe_query(f"""
                SELECT tool_name, COUNT(*) AS uses FROM {FROM} t
                WHERE tool_name IS NOT NULL AND tool_name != ''
                GROUP BY tool_name ORDER BY uses DESC LIMIT 10
            """)
            if not tools_df.empty:
                lines = [f"  {r['tool_name']}: {int(r['uses']):,}" for _, r in tools_df.iterrows()]
                self._update_stats("stats-tools", "\n".join(lines))
        except Exception:
            pass

        # Token usage
        try:
            tok_df = _safe_query(f"""
                SELECT source,
                       SUM(COALESCE(input_tokens, 0)) AS input_tokens,
                       SUM(COALESCE(output_tokens, 0)) AS output_tokens
                FROM {FROM} t GROUP BY source
            """)
            if not tok_df.empty:
                lines = []
                for _, r in tok_df.iterrows():
                    inp = int(r["input_tokens"])
                    out = int(r["output_tokens"])
                    lines.append(f"  {r['source']}: {inp:,} in / {out:,} out")
                self._update_stats("stats-tokens", "\n".join(lines))
        except Exception:
            pass

        # Recent activity
        try:
            act_df = _safe_query(f"""
                SELECT CAST(timestamp AS DATE) AS day, COUNT(*) AS messages
                FROM {FROM} t
                WHERE timestamp IS NOT NULL
                GROUP BY day ORDER BY day DESC LIMIT 7
            """)
            if not act_df.empty:
                lines = [f"  {r['day']}: {int(r['messages']):,} msgs" for _, r in act_df.iterrows()]
                self._update_stats("stats-activity", "\n".join(lines))
        except Exception:
            pass

    def _update_metric(self, metric_id: str, value: str) -> None:
        try:
            card = self.query_one(f"#{metric_id}", MetricCard)
            card.update_value(value)
        except Exception:
            pass

    def _update_stats(self, section_id: str, content: str) -> None:
        try:
            section = self.query_one(f"#{section_id}", StatsSection)
            section.update_content(content)
        except Exception:
            pass
