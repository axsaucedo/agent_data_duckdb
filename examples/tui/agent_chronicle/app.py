"""Main Textual App for Agent Chronicle TUI."""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Header, Footer, TabbedContent, TabPane, Static
from textual.containers import Vertical

from agent_chronicle.screens.overview import OverviewScreen
from agent_chronicle.screens.browser import BrowserScreen
from agent_chronicle.screens.sql import SQLScreen


HELP_TEXT = """\
[bold #a3e635]Agent Chronicle — Keyboard Shortcuts[/bold #a3e635]

[bold]Navigation[/bold]
  [#a3e635]1[/#a3e635]          Overview tab
  [#a3e635]2[/#a3e635]          Session Browser tab
  [#a3e635]3[/#a3e635]          SQL Query tab
  [#a3e635]Tab[/#a3e635]        Next tab
  [#a3e635]Shift+Tab[/#a3e635]  Previous tab

[bold]Session Browser[/bold]
  [#a3e635]↑ ↓[/#a3e635]       Navigate rows
  [#a3e635]Enter[/#a3e635]      Open session / select event
  [#a3e635]Escape[/#a3e635]     Back to session list

[bold]SQL Query[/bold]
  [#a3e635]F5[/#a3e635]         Execute query

[bold]General[/bold]
  [#a3e635]?[/#a3e635]          Toggle this help
  [#a3e635]q[/#a3e635]          Quit

[dim]Press Escape or ? to close[/dim]
"""


class HelpScreen(ModalScreen):
    """Modal help overlay."""

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }
    #help-dialog {
        background: #1e293b;
        border: tall #a3e635;
        padding: 2 4;
        width: 60;
        height: auto;
        max-height: 30;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("question_mark", "dismiss", "Close"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="help-dialog"):
            yield Static(HELP_TEXT)


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
                yield SQLScreen(self.claude_path, self.copilot_path)
        yield Footer()

    def action_switch_tab(self, tab_id: str) -> None:
        """Switch to a tab by id."""
        tabs = self.query_one("#tabs", TabbedContent)
        tabs.active = tab_id

    def action_toggle_help(self) -> None:
        """Toggle help overlay."""
        self.push_screen(HelpScreen())
