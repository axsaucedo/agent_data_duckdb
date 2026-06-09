#!/usr/bin/env python3
"""Resolve the DuckDB version/source id to stamp into extension metadata."""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def duckdb_source_id() -> str:
    import duckdb

    row = duckdb.connect().execute("PRAGMA version").fetchone()
    if row is None or len(row) < 2 or not row[1]:
        raise RuntimeError(f"Could not read DuckDB source id from PRAGMA version: {row!r}")
    return str(row[1])


def resolve_metadata_version(
    duckdb_git_version: str | None,
    default: str,
    source_id: Callable[[], str] = duckdb_source_id,
) -> str:
    version = (duckdb_git_version or "").strip()
    if not version:
        return default
    if version == "main":
        return source_id()
    return version


def default_metadata_version(makefile_path: Path = ROOT / "Makefile") -> str:
    text = makefile_path.read_text()
    match = re.search(r"^DEFAULT_TARGET_DUCKDB_VERSION\s*:?=\s*(.+)$", text, flags=re.MULTILINE)
    if not match:
        raise RuntimeError(f"Could not parse DEFAULT_TARGET_DUCKDB_VERSION from {makefile_path}")
    return match.group(1).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duckdb-git-version", default="")
    parser.add_argument("--default")
    args = parser.parse_args()

    try:
        print(resolve_metadata_version(args.duckdb_git_version, args.default or default_metadata_version()))
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
