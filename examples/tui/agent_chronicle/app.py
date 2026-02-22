"""Main Textual App for Agent Chronicle TUI."""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import Header, Footer, TabbedContent, TabPane, Static, DataTable, Input
from textual.containers import Vertical, VerticalScroll

from agent_chronicle.screens.overview import OverviewScreen
from agent_chronicle.screens.browser import BrowserScreen
from agent_chronicle.screens.sql import SQLScreen
from agent_chronicle.themes import THEMES, DEFAULT_THEME, THEME_NAMES


HELP_TEXT = """\
[bold]⌨  Agent Chronicle — Keyboard Reference[/bold]

[bold]Navigation[/bold]
  1  2  3       Jump to Browser / Overview / SQL tab
  Tab           Cycle focus forward
  Shift+Tab     Cycle focus backward

[bold]Vim Motions (in tables)[/bold]
  j  k          Move cursor down / up
  l  Enter      Open / drill into selection
  h  Escape     Go back / close detail

[bold]Session Browser[/bold]
  j  k          Navigate sessions or events
  l  Enter      Open session → timeline → event detail
  h  Escape     Back to session list
  /             Focus filter input

[bold]SQL Query[/bold]
  Enter         Execute query

[bold]General[/bold]
  t             Cycle theme
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
        Binding("1", "switch_tab('browser')", "Browser", show=True),
        Binding("2", "switch_tab('overview')", "Overview", show=True),
        Binding("3", "switch_tab('sql')", "SQL", show=True),
        Binding("j", "scroll_down", "↓", show=False),
        Binding("k", "scroll_up", "↑", show=False),
        Binding("t", "cycle_theme", "Theme", show=True),
        Binding("question_mark", "toggle_help", "Help", show=True),
        Binding("q", "quit", "Quit", show=True),
    ]

    def __init__(self, claude_path: str = "~/.claude", copilot_path: str = "~/.copilot", theme_name: str = DEFAULT_THEME):
        super().__init__()
        self.claude_path = claude_path
        self.copilot_path = copilot_path
        self._theme_name = theme_name
        for t in THEMES.values():
            self.register_theme(t)
        self.theme = self._theme_name

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
        tabs = self.query_one("#tabs", TabbedContent)
        tabs.active = tab_id

    def action_scroll_down(self) -> None:
        focused = self.focused
        if isinstance(focused, (Input,)):
            return
        if isinstance(focused, DataTable):
            focused.action_cursor_down()
        else:
            # Scroll the nearest scrollable ancestor
            for widget in self.screen.query("VerticalScroll"):
                if widget.is_on_screen:
                    widget.scroll_down(animate=False)
                    break

    def action_scroll_up(self) -> None:
        focused = self.focused
        if isinstance(focused, (Input,)):
            return
        if isinstance(focused, DataTable):
            focused.action_cursor_up()
        else:
            for widget in self.screen.query("VerticalScroll"):
                if widget.is_on_screen:
                    widget.scroll_up(animate=False)
                    break

    def action_cycle_theme(self) -> None:
        idx = THEME_NAMES.index(self.theme) if self.theme in THEME_NAMES else -1
        next_theme = THEME_NAMES[(idx + 1) % len(THEME_NAMES)]
        self.theme = next_theme
        self.notify(f"Theme: {next_theme}", timeout=2)

    def action_toggle_help(self) -> None:
        self.push_screen(HelpScreen())
