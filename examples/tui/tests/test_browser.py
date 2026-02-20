"""Tests for the Session Browser screen."""

import pytest
from agent_chronicle.app import AgentChronicle
from agent_chronicle.screens.browser import BrowserScreen
from textual.widgets import DataTable, Input


@pytest.fixture
def app():
    return AgentChronicle(claude_path="test_data/claude", copilot_path="test_data/copilot")


class TestBrowserScreen:
    @pytest.mark.asyncio
    async def test_browser_renders(self, app):
        async with app.run_test() as pilot:
            await pilot.press("2")
            browser = app.query_one(BrowserScreen)
            assert browser is not None

    @pytest.mark.asyncio
    async def test_session_table_exists(self, app):
        async with app.run_test() as pilot:
            await pilot.press("2")
            table = app.query_one("#session-table", DataTable)
            assert table is not None

    @pytest.mark.asyncio
    async def test_session_table_has_columns(self, app):
        async with app.run_test() as pilot:
            await pilot.press("2")
            table = app.query_one("#session-table", DataTable)
            assert len(table.columns) == 5

    @pytest.mark.asyncio
    async def test_session_table_has_rows(self, app):
        async with app.run_test() as pilot:
            await pilot.press("2")
            table = app.query_one("#session-table", DataTable)
            assert table.row_count > 0

    @pytest.mark.asyncio
    async def test_filter_input_exists(self, app):
        async with app.run_test() as pilot:
            await pilot.press("2")
            inp = app.query_one("#filter-input", Input)
            assert inp is not None
