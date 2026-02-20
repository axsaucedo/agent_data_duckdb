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
            # Help screen should be pushed
            assert len(app.screen_stack) > 1
