#!/usr/bin/env python3
"""Manual smoke test for the locally built agent_data extension."""

from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path

import duckdb


ROOT = Path(__file__).resolve().parents[1]
METADATA = ROOT / "duckdb-release.toml"


def metadata_duckdb_version() -> str:
    data = tomllib.loads(METADATA.read_text())
    return data["duckdb"]["python_version"]


def main() -> int:
    expected_duckdb = metadata_duckdb_version()
    if duckdb.__version__ != expected_duckdb:
        print(f"Expected DuckDB Python {expected_duckdb}, got {duckdb.__version__}", file=sys.stderr)
        return 1

    extension = Path(os.environ.get("AGENT_DATA_EXTENSION_PATH", ROOT / "build/debug/agent_data.duckdb_extension"))
    extension = extension.expanduser().resolve()
    if not extension.exists():
        print(f"Missing local extension: {extension}", file=sys.stderr)
        return 1

    con = duckdb.connect(config={"allow_unsigned_extensions": "true"})
    escaped_extension = extension.as_posix().replace("'", "''")
    con.execute(f"LOAD '{escaped_extension}'")

    checks = {
        "claude_conversations": "SELECT count(*) FROM read_conversations(path='test/data_claude', source='claude')",
        "copilot_conversations": "SELECT count(*) FROM read_conversations(path='test/data_copilot', source='copilot')",
        "claude_todos": "SELECT count(*) FROM read_todos(path='test/data_claude', source='claude')",
        "copilot_todos": "SELECT count(*) FROM read_todos(path='test/data_copilot', source='copilot')",
        "claude_plans": "SELECT count(*) FROM read_plans(path='test/data_claude', source='claude')",
        "copilot_plans": "SELECT count(*) FROM read_plans(path='test/data_copilot', source='copilot')",
        "claude_history": "SELECT count(*) FROM read_history(path='test/data_claude', source='claude')",
        "copilot_history": "SELECT count(*) FROM read_history(path='test/data_copilot', source='copilot')",
        "claude_stats": "SELECT count(*) FROM read_stats(path='test/data_claude', source='claude')",
        "copilot_stats": "SELECT count(*) FROM read_stats(path='test/data_copilot', source='copilot')",
        "autodetect_claude": "SELECT count(*) FROM read_conversations(path='test/data_claude')",
        "autodetect_copilot": "SELECT count(*) FROM read_conversations(path='test/data_copilot')",
    }

    results: dict[str, int] = {}
    for name, sql in checks.items():
        count = con.execute(sql).fetchone()[0]
        results[name] = count
        print(f"{name}={count}")

    expected_positive = [name for name in checks if name != "copilot_stats"]
    missing = [name for name in expected_positive if results[name] <= 0]
    if missing:
        print(f"Expected positive row counts for: {', '.join(missing)}", file=sys.stderr)
        return 1
    if results["copilot_stats"] != 0:
        print("Expected copilot_stats=0 because stats are Claude-only", file=sys.stderr)
        return 1

    print("manual_smoke=pass")
    return 0


if __name__ == "__main__":
    sys.exit(main())
