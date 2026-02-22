"""Tests for the Overview screen."""

import pytest
from agent_chronicle.app import AgentChronicle
from agent_chronicle.screens.overview import OverviewScreen, MetricCard, ChartSection, ActivitySparkSection
from textual.widgets import Static


@pytest.fixture
def app():
    return AgentChronicle(claude_path="test_data/claude", copilot_path="test_data/copilot")


class TestOverviewScreen:
    @pytest.mark.asyncio
    async def test_overview_renders(self, app):
        async with app.run_test() as pilot:
            overview = app.query_one(OverviewScreen)
            assert overview is not None

    @pytest.mark.asyncio
    async def test_has_metric_cards(self, app):
        async with app.run_test() as pilot:
            cards = app.query(MetricCard)
            assert len(cards) == 4

    @pytest.mark.asyncio
    async def test_has_chart_sections(self, app):
        async with app.run_test() as pilot:
            sections = app.query(ChartSection)
            assert len(sections) == 6

    @pytest.mark.asyncio
    async def test_has_activity_sparkline(self, app):
        async with app.run_test() as pilot:
            spark = app.query_one(ActivitySparkSection)
            assert spark is not None

    @pytest.mark.asyncio
    async def test_overview_title_present(self, app):
        async with app.run_test() as pilot:
            title = app.query_one("#overview-title", Static)
            assert title is not None

    @pytest.mark.asyncio
    async def test_bar_chart_rendering(self):
        from agent_chronicle.screens.overview import _bar_chart_lines
        items = [("tool_a", 100), ("tool_b", 50)]
        output = _bar_chart_lines(items)
        assert "tool_a" in output
        assert "tool_b" in output
        assert "100" in output
        assert "█" in output
