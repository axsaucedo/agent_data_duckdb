"""Tests for the Overview screen."""

import pytest
from agent_chronicle.app import AgentChronicle
from agent_chronicle.screens.overview import OverviewScreen, MetricCard, StatsSection
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
    async def test_has_stats_sections(self, app):
        async with app.run_test() as pilot:
            sections = app.query(StatsSection)
            assert len(sections) == 6

    @pytest.mark.asyncio
    async def test_overview_title_present(self, app):
        async with app.run_test() as pilot:
            title = app.query_one("#overview-title", Static)
            # Static.render() returns the display text
            assert title is not None
