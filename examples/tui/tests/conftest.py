"""Test fixtures for Agent Chronicle TUI tests."""

import os
import pytest
from pathlib import Path

# Test data directories
TEST_DATA_DIR = Path(__file__).parent.parent / "test_data"
CLAUDE_TEST_PATH = str(TEST_DATA_DIR / "claude")
COPILOT_TEST_PATH = str(TEST_DATA_DIR / "copilot")


@pytest.fixture(autouse=True)
def set_test_paths(monkeypatch):
    """Set environment variables to point at synthetic test data."""
    monkeypatch.setenv("AGENT_DATA_CLAUDE_PATH", CLAUDE_TEST_PATH)
    monkeypatch.setenv("AGENT_DATA_COPILOT_PATH", COPILOT_TEST_PATH)


@pytest.fixture
def claude_path():
    return CLAUDE_TEST_PATH


@pytest.fixture
def copilot_path():
    return COPILOT_TEST_PATH
