#!/usr/bin/env python3
"""Tests for duckdb_metadata_version.py."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import duckdb_metadata_version


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "duckdb_metadata_version.py"


class DuckDBMetadataVersionTests(unittest.TestCase):
    def test_default_without_duckdb_git_version(self) -> None:
        self.assertEqual(
            duckdb_metadata_version.resolve_metadata_version("", "v1.5.3", lambda: "unexpected"),
            "v1.5.3",
        )

    def test_release_ref_uses_ref(self) -> None:
        self.assertEqual(
            duckdb_metadata_version.resolve_metadata_version("v1.5.3", "v1.5.2", lambda: "unexpected"),
            "v1.5.3",
        )

    def test_main_uses_duckdb_source_id(self) -> None:
        self.assertEqual(
            duckdb_metadata_version.resolve_metadata_version("main", "v1.5.3", lambda: "abc123"),
            "abc123",
        )

    def test_main_source_id_failure_is_not_silent(self) -> None:
        def fail() -> str:
            raise RuntimeError("missing duckdb")

        with self.assertRaisesRegex(RuntimeError, "missing duckdb"):
            duckdb_metadata_version.resolve_metadata_version("main", "v1.5.3", fail)

    def test_cli_default_path_does_not_import_duckdb(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--default", "v1.5.3"],
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.stdout.strip(), "v1.5.3")

    def test_default_metadata_version_reads_makefile_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            makefile = Path(temp_dir) / "Makefile"
            makefile.write_text("DEFAULT_TARGET_DUCKDB_VERSION := v1.5.4\n")
            self.assertEqual(duckdb_metadata_version.default_metadata_version(makefile), "v1.5.4")

    def test_duckdb_source_id_falls_back_to_git(self) -> None:
        with mock.patch.object(
            duckdb_metadata_version,
            "duckdb_python_source_id",
            side_effect=RuntimeError("missing duckdb"),
        ):
            with mock.patch.object(duckdb_metadata_version, "duckdb_git_source_id", return_value="abcdef1234"):
                self.assertEqual(duckdb_metadata_version.duckdb_source_id(), "abcdef1234")

    def test_duckdb_source_id_reports_all_failures(self) -> None:
        with mock.patch.object(
            duckdb_metadata_version,
            "duckdb_python_source_id",
            side_effect=RuntimeError("missing duckdb"),
        ):
            with mock.patch.object(
                duckdb_metadata_version,
                "duckdb_git_source_id",
                side_effect=RuntimeError("missing git checkout"),
            ):
                with self.assertRaisesRegex(RuntimeError, "missing duckdb.*missing git checkout"):
                    duckdb_metadata_version.duckdb_source_id()


if __name__ == "__main__":
    unittest.main()
