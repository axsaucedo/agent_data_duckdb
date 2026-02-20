"""Main Textual App for Agent Chronicle TUI."""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer, TabbedContent, TabPane, Static

from agent_chronicle.screens.overview import OverviewScreen
from agent_chronicle.screens.browser import BrowserScreen


class AgentChronicle(App):
    """Agent Chronicle — Terminal explorer for AI agent session data."""

    TITLE = "Agent Chronicle"
    SUB_TITLE = "AI agent session explorer"
    CSS_PATH = "theme.tcss"

    BINDINGS = [
        Binding("1", "switch_tab('overview')", "Overview", show=True),
        Binding("2", "switch_tab('browser')", "Browser", show=True),
        Binding("3", "switch_tab('sql')", "SQL", show=True),
        Binding("question_mark", "toggle_help", "Help", show=True),
        Binding("q", "quit", "Quit", show=True),
    ]

    def __init__(self, claude_path: str = "~/.claude", copilot_path: str = "~/.copilot"):
        super().__init__()
        self.claude_path = claude_path
        self.copilot_path = copilot_path

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(id="tabs"):
            with TabPane("📊 Overview", id="overview"):
                yield OverviewScreen(self.claude_path, self.copilot_path)
            with TabPane("📋 Browser", id="browser"):
                yield BrowserScreen(self.claude_path, self.copilot_path)
            with TabPane("🔎 SQL", id="sql"):
                yield Static("SQL Query — loading…", id="sql-content")
        yield Footer()

    def action_switch_tab(self, tab_id: str) -> None:
        """Switch to a tab by id."""
        tabs = self.query_one("#tabs", TabbedContent)
        tabs.active = tab_id

    def action_toggle_help(self) -> None:
        """Toggle help overlay."""
        self.notify(
            "Keyboard shortcuts:\n"
            "  1/2/3 — Switch tabs\n"
            "  Tab — Next tab\n"
            "  q — Quit\n"
            "  ? — This help",
            title="Help",
            timeout=8,
        )
