"""Main Textual App for Agent Chronicle TUI."""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Header, Footer, TabbedContent, TabPane, Static, DataTable
from textual.containers import Vertical, VerticalScroll

from agent_chronicle.screens.overview import OverviewScreen
from agent_chronicle.screens.browser import BrowserScreen
from agent_chronicle.screens.sql import SQLScreen
from agent_chronicle.themes import THEME


HELP_TEXT = """\
[bold]⌨  Agent Chronicle — Keyboard Reference[/bold]

[bold]Navigation[/bold]
  1  2  3       Jump to Browser / Overview / SQL tab
  Tab           Cycle focus forward
  Shift+Tab     Cycle focus backward

[bold]Vim Motions[/bold]
  j  k          Move cursor down / up (tables, lists, scrollable panels)
  l  Enter      Open / drill into selection
  h  Escape     Go back / close detail

[bold]Session Browser[/bold]
  j  k          Navigate sessions, events, or scroll detail
  l  Enter      Open session → timeline → event detail
  h  Escape     Back to session list
  /             Focus filter input

[bold]SQL Query[/bold]
  Enter         Execute query
  s             Toggle samples panel (when not in editor)
  j  k          Navigate results or samples table

[bold]General[/bold]
  ?             Toggle this help
  q             Quit

Press ? or Escape to close
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
        Binding("1", "switch_tab('browser')", "Browser", show=True, priority=True),
        Binding("2", "switch_tab('overview')", "Overview", show=True, priority=True),
        Binding("3", "switch_tab('sql')", "SQL", show=True, priority=True),
        Binding("question_mark", "toggle_help", "Help", show=True, priority=True),
        Binding("q", "quit", "Quit", show=True, priority=True),
    ]

    def __init__(self, claude_path: str = "~/.claude", copilot_path: str = "~/.copilot", **kwargs):
        # Pop theme_name if passed (backwards compat) but ignore it
        kwargs.pop("theme_name", None)
        super().__init__(**kwargs)
        self.claude_path = claude_path
        self.copilot_path = copilot_path
        self.register_theme(THEME)
        self.theme = "tokyo-night"

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(id="tabs"):
            with TabPane("📋 Browser", id="browser"):
                yield BrowserScreen(self.claude_path, self.copilot_path)
            with TabPane("📊 Overview", id="overview"):
                yield OverviewScreen(self.claude_path, self.copilot_path)
            with TabPane("🔎 SQL", id="sql"):
                yield SQLScreen(self.claude_path, self.copilot_path)
        yield Footer()

    def action_switch_tab(self, tab_id: str) -> None:
        self.query_one("#tabs", TabbedContent).active = tab_id

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        """Restore focus to the correct widget after any tab switch."""
        tab_id = event.tabbed_content.active
        self._refocus_active_tab(tab_id)

    def _refocus_active_tab(self, tab_id: str) -> None:
        try:
            if tab_id == "browser":
                self.query_one(BrowserScreen).restore_focus()
            elif tab_id == "overview":
                self.query_one("#overview-scroll", VerticalScroll).focus()
            elif tab_id == "sql":
                self.query_one(SQLScreen).restore_focus()
        except Exception:
            pass

    def action_toggle_help(self) -> None:
        self.push_screen(HelpScreen())
