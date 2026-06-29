#!/usr/bin/env python3
"""Tests for update_duckdb_release.py."""

from __future__ import annotations

import subprocess
import sys
import unittest
from unittest import mock

import update_duckdb_release
from update_duckdb_release import ReleaseTarget

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "update_duckdb_release.py"


class ConsistencyCheckTests(unittest.TestCase):
    def test_repo_tree_is_internally_consistent(self) -> None:
        self.assertEqual(update_duckdb_release.consistency_mismatches(), [])

    def test_consistency_check_does_not_use_network(self) -> None:
        def fail(*_args, **_kwargs):
            raise AssertionError("consistency check must not contact the network")

        with mock.patch.object(update_duckdb_release, "http_json", side_effect=fail):
            self.assertEqual(update_duckdb_release.consistency_mismatches(), [])

    def test_desynced_metadata_is_detected(self) -> None:
        bogus = ReleaseTarget(
            duckdb_version="v9.9.9",
            python_version="9.9.9",
            crate_version="9.99999.0",
            ci_tools_ref="v9.9-bogus",
            excluded_archs="none",
        )
        with mock.patch.object(update_duckdb_release, "read_metadata", return_value=bogus):
            mismatches = update_duckdb_release.consistency_mismatches()
        self.assertTrue(mismatches)
        # Metadata keys describe the source of truth itself and must never be reported.
        self.assertFalse(any(item.startswith("metadata.") for item in mismatches))
        self.assertTrue(any(item.startswith("makefile.") for item in mismatches))

    def test_cli_check_consistency_passes_on_repo(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--check-consistency"],
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertIn("internally consistent", result.stdout)

    def test_cli_rejects_multiple_modes(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--check", "--check-consistency"],
            text=True,
            capture_output=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("exactly one of", result.stderr)


if __name__ == "__main__":
    unittest.main()
