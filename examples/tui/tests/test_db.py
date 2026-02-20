"""Tests for the data layer (db.py)."""

import pytest
import pandas as pd

from agent_chronicle.db import (
    get_connection,
    get_data_paths,
    run_query,
    load_session_index,
    load_session_events,
    reset_connection,
    union_from,
    path_expr,
)


class TestConnection:
    def test_get_connection_returns_valid(self):
        reset_connection()
        con = get_connection()
        result = con.execute("SELECT 1 AS val").df()
        assert result["val"].iloc[0] == 1

    def test_get_data_paths_defaults(self, monkeypatch):
        monkeypatch.delenv("AGENT_DATA_CLAUDE_PATH", raising=False)
        monkeypatch.delenv("AGENT_DATA_COPILOT_PATH", raising=False)
        claude, copilot = get_data_paths()
        assert claude == "~/.claude"
        assert copilot == "~/.copilot"

    def test_get_data_paths_from_env(self):
        claude, copilot = get_data_paths()
        assert "test_data/claude" in claude
        assert "test_data/copilot" in copilot


class TestQueries:
    def test_run_query_basic(self):
        reset_connection()
        df = run_query("SELECT 42 AS answer")
        assert df["answer"].iloc[0] == 42

    def test_load_session_index_claude(self, claude_path):
        reset_connection()
        df = load_session_index(claude_path)
        assert isinstance(df, pd.DataFrame)
        if not df.empty:
            assert "session_id" in df.columns
            assert "source" in df.columns
            assert "event_count" in df.columns

    def test_load_session_index_copilot(self, copilot_path):
        reset_connection()
        df = load_session_index(copilot_path)
        assert isinstance(df, pd.DataFrame)
        if not df.empty:
            assert "session_id" in df.columns

    def test_load_session_events_returns_dataframe(self, claude_path):
        reset_connection()
        idx = load_session_index(claude_path)
        if not idx.empty:
            sid = idx["session_id"].iloc[0]
            events = load_session_events(claude_path, sid)
            assert isinstance(events, pd.DataFrame)
            if not events.empty:
                assert "message_type" in events.columns


class TestHelpers:
    def test_union_from(self):
        result = union_from("/a", "/b", "read_conversations")
        assert "UNION ALL" in result
        assert "/a" in result
        assert "/b" in result

    def test_path_expr_claude(self):
        result = path_expr("claude", "read_conversations", "/a", "/b")
        assert "/a" in result
        assert "UNION" not in result

    def test_path_expr_copilot(self):
        result = path_expr("copilot", "read_conversations", "/a", "/b")
        assert "/b" in result

    def test_path_expr_both(self):
        result = path_expr("both", "read_conversations", "/a", "/b")
        assert "UNION ALL" in result
