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
[bold #a6e3a1]⌨  Agent Chronicle — Keyboard Reference[/bold #a6e3a1]

[bold #89b4fa]Navigation[/bold #89b4fa]
  [#a6e3a1]1  2  3[/#a6e3a1]       Jump to Overview / Browser / SQL tab
  [#a6e3a1]H  L[/#a6e3a1]          Previous / Next focus  (Shift+h / Shift+l)
  [#a6e3a1]Tab[/#a6e3a1]           Cycle focus forward
  [#a6e3a1]Shift+Tab[/#a6e3a1]     Cycle focus backward

[bold #89b4fa]Vim Motions (in tables)[/bold #89b4fa]
  [#a6e3a1]j  k[/#a6e3a1]          Move cursor down / up
  [#a6e3a1]l  Enter[/#a6e3a1]      Open / drill into selection
  [#a6e3a1]h  Escape[/#a6e3a1]     Go back / close detail

[bold #89b4fa]Session Browser[/bold #89b4fa]
  [#a6e3a1]j  k[/#a6e3a1]          Navigate sessions or events
  [#a6e3a1]l  Enter[/#a6e3a1]      Open session → timeline → event detail
  [#a6e3a1]h  Escape[/#a6e3a1]     Back to session list
  [#a6e3a1]/[/#a6e3a1]             Focus filter input

[bold #89b4fa]SQL Query[/bold #89b4fa]
  [#a6e3a1]F5[/#a6e3a1]            Execute query
  [#a6e3a1]Ctrl+Enter[/#a6e3a1]    Execute query (alt)

[bold #89b4fa]General[/bold #89b4fa]
  [#a6e3a1]?[/#a6e3a1]             Toggle this help
  [#a6e3a1]q[/#a6e3a1]             Quit

[dim #6c7086]Press ? or Escape to close[/dim #6c7086]
"""


class HelpScreen(ModalScreen):
    """Modal help overlay."""

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
        Binding("H", "focus_previous", "←Focus", show=False),
        Binding("L", "focus_next", "Focus→", show=False),
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
        tabs = self.query_one("#tabs", TabbedContent)
        tabs.active = tab_id

    def action_toggle_help(self) -> None:
        self.push_screen(HelpScreen())
