"""Tests for the SQL Query screen."""

import pytest
from agent_chronicle.app import AgentChronicle
from agent_chronicle.screens.sql import SQLScreen
from textual.widgets import DataTable, TextArea, Button, Select


@pytest.fixture
def app():
    return AgentChronicle(claude_path="test_data/claude", copilot_path="test_data/copilot")


class TestSQLScreen:
    @pytest.mark.asyncio
    async def test_sql_screen_renders(self, app):
        async with app.run_test() as pilot:
            await pilot.press("3")
            sql_screen = app.query_one(SQLScreen)
            assert sql_screen is not None

    @pytest.mark.asyncio
    async def test_sql_editor_exists(self, app):
        async with app.run_test() as pilot:
            await pilot.press("3")
            editor = app.query_one("#sql-editor", TextArea)
            assert editor is not None

    @pytest.mark.asyncio
    async def test_sql_editor_has_default_query(self, app):
        async with app.run_test() as pilot:
            await pilot.press("3")
            editor = app.query_one("#sql-editor", TextArea)
            assert "read_conversations" in editor.text

    @pytest.mark.asyncio
    async def test_run_button_exists(self, app):
        async with app.run_test() as pilot:
            await pilot.press("3")
            btn = app.query_one("#sql-run-btn", Button)
            assert btn is not None

    @pytest.mark.asyncio
    async def test_source_select_exists(self, app):
        async with app.run_test() as pilot:
            await pilot.press("3")
            sel = app.query_one("#sql-source-select", Select)
            assert sel is not None

    @pytest.mark.asyncio
    async def test_results_table_exists(self, app):
        async with app.run_test() as pilot:
            await pilot.press("3")
            table = app.query_one("#sql-results", DataTable)
            assert table is not None

    @pytest.mark.asyncio
    async def test_samples_table_exists(self, app):
        async with app.run_test() as pilot:
            await pilot.press("3")
            table = app.query_one("#samples-table", DataTable)
            assert table is not None
            assert table.row_count > 0

    @pytest.mark.asyncio
    async def test_samples_toggle(self, app):
        """Test s key toggles between query and samples view."""
        async with app.run_test() as pilot:
            await pilot.press("3")
            await pilot.pause()
            sql = app.query_one(SQLScreen)
            # Focus the results table first (not the TextArea, as s is captured there)
            app.query_one("#sql-results", DataTable).focus()
            await pilot.pause()
            await pilot.press("s")
            await pilot.pause()
            assert sql._showing_samples is True
            assert app.query_one("#sql-samples-view").display is True

    @pytest.mark.asyncio
    async def test_vim_bindings_exist(self, app):
        async with app.run_test() as pilot:
            await pilot.press("3")
            sql = app.query_one(SQLScreen)
            assert hasattr(sql, "action_vim_down")
            assert hasattr(sql, "action_vim_up")
            assert hasattr(sql, "action_toggle_samples")
