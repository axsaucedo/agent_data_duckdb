"""Tests for app navigation and tab switching."""

import pytest
from agent_chronicle.app import AgentChronicle
from textual.widgets import TabbedContent


@pytest.fixture
def app():
    return AgentChronicle(claude_path="test_data/claude", copilot_path="test_data/copilot")


class TestNavigation:
    @pytest.mark.asyncio
    async def test_app_starts(self, app):
        async with app.run_test() as pilot:
            assert app.title == "Agent Chronicle"

    @pytest.mark.asyncio
    async def test_has_three_tabs(self, app):
        async with app.run_test() as pilot:
            tabs = app.query_one("#tabs", TabbedContent)
            panes = list(tabs.query("TabPane"))
            assert len(panes) == 3

    @pytest.mark.asyncio
    async def test_switch_to_browser_tab(self, app):
        async with app.run_test() as pilot:
            await pilot.press("2")
            tabs = app.query_one("#tabs", TabbedContent)
            assert tabs.active == "browser"

    @pytest.mark.asyncio
    async def test_switch_to_sql_tab(self, app):
        async with app.run_test() as pilot:
            await pilot.press("3")
            tabs = app.query_one("#tabs", TabbedContent)
            assert tabs.active == "sql"

    @pytest.mark.asyncio
    async def test_switch_to_overview_tab(self, app):
        async with app.run_test() as pilot:
            await pilot.press("2")
            await pilot.press("1")
            tabs = app.query_one("#tabs", TabbedContent)
            assert tabs.active == "overview"

    @pytest.mark.asyncio
    async def test_help_overlay(self, app):
        async with app.run_test() as pilot:
            await pilot.press("question_mark")
            assert len(app.screen_stack) > 1

    @pytest.mark.asyncio
    async def test_shift_l_next_tab(self, app):
        async with app.run_test() as pilot:
            await pilot.press("1")
            tabs = app.query_one("#tabs", TabbedContent)
            assert tabs.active == "overview"
            await pilot.press("L")
            assert tabs.active == "browser"

    @pytest.mark.asyncio
    async def test_shift_h_prev_tab(self, app):
        async with app.run_test() as pilot:
            await pilot.press("2")
            tabs = app.query_one("#tabs", TabbedContent)
            assert tabs.active == "browser"
            await pilot.press("H")
            assert tabs.active == "overview"

    @pytest.mark.asyncio
    async def test_shift_j_cycles_focus_next(self, app):
        async with app.run_test() as pilot:
            await pilot.press("J")
            assert app.title == "Agent Chronicle"

    @pytest.mark.asyncio
    async def test_shift_k_cycles_focus_prev(self, app):
        async with app.run_test() as pilot:
            await pilot.press("K")
            assert app.title == "Agent Chronicle"


class TestThemes:
    @pytest.fixture
    def app(self):
        return AgentChronicle(claude_path="test_data/claude", copilot_path="test_data/copilot")

    @pytest.mark.asyncio
    async def test_default_theme_is_catppuccin(self, app):
        async with app.run_test() as pilot:
            assert app.theme == "catppuccin-mocha"

    @pytest.mark.asyncio
    async def test_custom_theme_from_init(self):
        app = AgentChronicle(claude_path="test_data/claude", copilot_path="test_data/copilot", theme_name="dracula")
        async with app.run_test() as pilot:
            assert app.theme == "dracula"

    @pytest.mark.asyncio
    async def test_cycle_theme(self, app):
        async with app.run_test() as pilot:
            assert app.theme == "catppuccin-mocha"
            await pilot.press("t")
            assert app.theme == "dracula"
            await pilot.press("t")
            assert app.theme == "nord"

    @pytest.mark.asyncio
    async def test_all_themes_registered(self, app):
        from agent_chronicle.themes import THEME_NAMES
        async with app.run_test() as pilot:
            for name in THEME_NAMES:
                app.theme = name
                assert app.theme == name
