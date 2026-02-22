"""Overview dashboard screen with metrics and visual charts."""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Static, Sparkline
from textual.worker import WorkerState
from textual import work

from agent_chronicle.db import union_from, _run_queries_threaded

# Unicode bar characters for horizontal bar charts
BAR_CHARS = " ▏▎▍▌▋▊▉█"


def _bar(value: float, max_value: float, width: int = 25) -> str:
    """Render a horizontal bar using Unicode block characters."""
    if max_value <= 0:
        return ""
    ratio = min(value / max_value, 1.0)
    full_blocks = int(ratio * width)
    remainder = (ratio * width) - full_blocks
    partial_idx = int(remainder * 8)
    bar = "█" * full_blocks
    if partial_idx > 0 and full_blocks < width:
        bar += BAR_CHARS[partial_idx]
    return bar


def _bar_chart_lines(items: list[tuple[str, int]], color: str = "$primary") -> str:
    """Render a labeled horizontal bar chart as Rich markup."""
    if not items:
        return "[dim]No data[/dim]"
    max_val = max(v for _, v in items) if items else 1
    max_label = max(len(lbl) for lbl, _ in items) if items else 10
    lines = []
    for label, value in items:
        bar = _bar(value, max_val)
        lines.append(f"  {label:<{max_label}}  [{color}]{bar}[/{color}] {value:,}")
    return "\n".join(lines)


class MetricCard(Static):
    """A single metric card with label and value."""

    DEFAULT_CSS = """
    MetricCard {
        background: $surface 70%;
        border: round $surface 70%;
        padding: 1 2;
        margin: 0 1;
        height: 5;
        width: 1fr;
    }
    .metric-value {
        text-style: bold;
        color: $primary;
    }
    .metric-label {
        color: $foreground 60%;
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


class ChartSection(Static):
    """A section with a title and chart content."""

    DEFAULT_CSS = """
    ChartSection {
        background: $surface 70%;
        border: round $surface 70%;
        padding: 1 2;
        margin: 1 1;
        height: auto;
        min-height: 5;
        width: 1fr;
    }
    """

    def __init__(self, title: str, content: str = "[dim]Loading…[/dim]", **kwargs):
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


class ActivitySparkSection(Static):
    """Section with a sparkline chart for activity over time."""

    DEFAULT_CSS = """
    ActivitySparkSection {
        background: $surface 70%;
        border: round $surface 70%;
        padding: 1 2;
        margin: 1 1;
        height: auto;
        min-height: 8;
        width: 1fr;
    }
    #activity-spark {
        height: 3;
        margin: 1 0 0 0;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._labels_text = ""

    def compose(self) -> ComposeResult:
        yield Static("[bold]📈 Activity (Last 14 Days)[/bold]")
        yield Sparkline([], id="activity-spark", min_color="#45475a", max_color="#89b4fa")
        yield Static("", id="activity-labels")

    def set_data(self, data: list[float], labels: list[str]) -> None:
        try:
            spark = self.query_one("#activity-spark", Sparkline)
            spark.data = data if data else [0]
            label_w = self.query_one("#activity-labels", Static)
            if labels:
                first, last = labels[0], labels[-1]
                label_w.update(f"  [dim]{first}[/dim]{'':>{max(0, 30)}}[dim]{last}[/dim]")
        except Exception:
            pass


class OverviewScreen(Static):
    """Overview dashboard with metrics and visual charts."""

    DEFAULT_CSS = """
    OverviewScreen {
        height: 1fr;
    }
    #overview-scroll {
        height: 1fr;
    }
    #overview-title {
        text-style: bold;
        color: $primary;
        padding: 0 0 1 0;
    }
    #metrics-row {
        height: 5;
        margin: 0 0 1 0;
    }
    #charts-grid {
        height: auto;
    }
    .charts-row {
        height: auto;
        margin: 0;
    }
    """

    BINDINGS = [
        Binding("j", "scroll_down", "Down", show=False),
        Binding("k", "scroll_up", "Up", show=False),
    ]

    def __init__(self, claude_path: str, copilot_path: str, **kwargs):
        super().__init__(**kwargs)
        self.claude_path = claude_path
        self.copilot_path = copilot_path

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="overview-scroll"):
            yield Static("🤖 Agent Chronicle — Overview", id="overview-title")
            with Horizontal(id="metrics-row"):
                yield MetricCard("Claude Sessions", "…", id="metric-claude-sessions")
                yield MetricCard("Claude Messages", "…", id="metric-claude-messages")
                yield MetricCard("Copilot Sessions", "…", id="metric-copilot-sessions")
                yield MetricCard("Copilot Messages", "…", id="metric-copilot-messages")
            yield ActivitySparkSection(id="activity-spark-section")
            with Vertical(id="charts-grid"):
                with Horizontal(classes="charts-row"):
                    yield ChartSection("💬 Message Types (Top 10)", id="chart-types")
                    yield ChartSection("🔧 Top Tools", id="chart-tools")
                with Horizontal(classes="charts-row"):
                    yield ChartSection("📁 Top Projects", id="chart-projects")
                    yield ChartSection("🕐 Sessions by Day", id="chart-sessions-day")
                with Horizontal(classes="charts-row"):
                    yield ChartSection("🔢 Token Usage", id="chart-tokens")
                    yield ChartSection("📊 Messages by Source", id="chart-source")

    def action_scroll_down(self) -> None:
        try:
            self.query_one("#overview-scroll", VerticalScroll).scroll_down(animate=False)
        except Exception:
            pass

    def action_scroll_up(self) -> None:
        try:
            self.query_one("#overview-scroll", VerticalScroll).scroll_up(animate=False)
        except Exception:
            pass

    def on_mount(self) -> None:
        self._load_data()

    @work(thread=True, exclusive=True)
    def _load_data(self) -> dict:
        """Load overview data in a background thread."""
        FROM = union_from(self.claude_path, self.copilot_path, "read_conversations")
        queries = {
            "metrics": f"""
                SELECT source,
                       COUNT(DISTINCT session_id) AS sessions,
                       COUNT(*) AS messages
                FROM {FROM} t
                GROUP BY source
            """,
            "sources": f"SELECT source, COUNT(*) AS messages FROM {FROM} t GROUP BY source",
            "types": f"""
                SELECT message_type, COUNT(*) AS count FROM {FROM} t
                WHERE message_type IS NOT NULL
                GROUP BY message_type ORDER BY count DESC LIMIT 10
            """,
            "projects": f"""
                SELECT COALESCE(SPLIT_PART(project_path, '/', -1), 'unknown') AS project,
                       COUNT(*) AS messages
                FROM {FROM} t
                WHERE project_path IS NOT NULL AND project_path != ''
                GROUP BY project ORDER BY messages DESC LIMIT 10
            """,
            "tools": f"""
                SELECT tool_name, COUNT(*) AS uses FROM {FROM} t
                WHERE tool_name IS NOT NULL AND tool_name != ''
                GROUP BY tool_name ORDER BY uses DESC LIMIT 10
            """,
            "tokens": f"""
                SELECT source,
                       SUM(COALESCE(input_tokens, 0)) AS input_tokens,
                       SUM(COALESCE(output_tokens, 0)) AS output_tokens
                FROM {FROM} t GROUP BY source
            """,
            "activity": f"""
                SELECT CAST(timestamp AS DATE) AS day, COUNT(*) AS messages
                FROM {FROM} t
                WHERE timestamp IS NOT NULL
                GROUP BY day ORDER BY day ASC LIMIT 14
            """,
            "sessions_by_day": f"""
                SELECT CAST(timestamp AS DATE) AS day,
                       COUNT(DISTINCT session_id) AS sessions
                FROM {FROM} t
                WHERE timestamp IS NOT NULL
                GROUP BY day ORDER BY day DESC LIMIT 7
            """,
        }
        return _run_queries_threaded(queries)

    def on_worker_state_changed(self, event) -> None:
        if event.state == WorkerState.SUCCESS and event.worker.result:
            self._apply_results(event.worker.result)

    def _apply_results(self, results: dict) -> None:
        """Apply query results to the UI with visual charts."""
        # Metric cards
        metrics_df = results.get("metrics")
        if metrics_df is not None and not metrics_df.empty:
            claude = metrics_df[metrics_df["source"] == "claude"]
            copilot = metrics_df[metrics_df["source"] == "copilot"]
            self._update_metric("metric-claude-sessions", str(int(claude["sessions"].iloc[0])) if not claude.empty else "0")
            self._update_metric("metric-claude-messages", str(int(claude["messages"].iloc[0])) if not claude.empty else "0")
            self._update_metric("metric-copilot-sessions", str(int(copilot["sessions"].iloc[0])) if not copilot.empty else "0")
            self._update_metric("metric-copilot-messages", str(int(copilot["messages"].iloc[0])) if not copilot.empty else "0")

        # Activity sparkline
        act_df = results.get("activity")
        if act_df is not None and not act_df.empty:
            data = [float(r["messages"]) for _, r in act_df.iterrows()]
            labels = [str(r["day"]) for _, r in act_df.iterrows()]
            try:
                section = self.query_one("#activity-spark-section", ActivitySparkSection)
                section.set_data(data, labels)
            except Exception:
                pass

        # Bar chart: messages by source
        src_df = results.get("sources")
        if src_df is not None and not src_df.empty:
            items = [(r["source"], int(r["messages"])) for _, r in src_df.iterrows()]
            self._update_chart("chart-source", _bar_chart_lines(items, "bold #89b4fa"))

        # Bar chart: message types
        types_df = results.get("types")
        if types_df is not None and not types_df.empty:
            items = [(r["message_type"], int(r["count"])) for _, r in types_df.iterrows()]
            self._update_chart("chart-types", _bar_chart_lines(items, "bold #a6e3a1"))

        # Bar chart: top projects
        proj_df = results.get("projects")
        if proj_df is not None and not proj_df.empty:
            items = [(r["project"], int(r["messages"])) for _, r in proj_df.iterrows()]
            self._update_chart("chart-projects", _bar_chart_lines(items, "bold #f9e2af"))

        # Bar chart: top tools
        tools_df = results.get("tools")
        if tools_df is not None and not tools_df.empty:
            items = [(r["tool_name"], int(r["uses"])) for _, r in tools_df.iterrows()]
            self._update_chart("chart-tools", _bar_chart_lines(items, "bold #cba6f7"))

        # Token usage with dual bars
        tok_df = results.get("tokens")
        if tok_df is not None and not tok_df.empty:
            lines = []
            all_vals = []
            for _, r in tok_df.iterrows():
                all_vals.extend([int(r["input_tokens"]), int(r["output_tokens"])])
            max_tok = max(all_vals) if all_vals else 1
            for _, r in tok_df.iterrows():
                inp, out = int(r["input_tokens"]), int(r["output_tokens"])
                inp_bar = _bar(inp, max_tok, 20)
                out_bar = _bar(out, max_tok, 20)
                lines.append(f"  {r['source']} input  [bold #89b4fa]{inp_bar}[/bold #89b4fa] {inp:,}")
                lines.append(f"  {r['source']} output [bold #a6e3a1]{out_bar}[/bold #a6e3a1] {out:,}")
            self._update_chart("chart-tokens", "\n".join(lines))

        # Sessions by day bar chart
        sbd_df = results.get("sessions_by_day")
        if sbd_df is not None and not sbd_df.empty:
            items = [(str(r["day"]), int(r["sessions"])) for _, r in sbd_df.iterrows()]
            self._update_chart("chart-sessions-day", _bar_chart_lines(items, "bold #f38ba8"))

    def _update_metric(self, metric_id: str, value: str) -> None:
        try:
            card = self.query_one(f"#{metric_id}", MetricCard)
            card.update_value(value)
        except Exception:
            pass

    def _update_chart(self, section_id: str, content: str) -> None:
        try:
            section = self.query_one(f"#{section_id}", ChartSection)
            section.update_content(content)
        except Exception:
            pass
