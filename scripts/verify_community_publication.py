#!/usr/bin/env python3
"""Verify agent_data is publicly published for the configured DuckDB release."""

from __future__ import annotations

import argparse
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PLATFORMS = ["osx_arm64", "osx_amd64", "linux_amd64", "linux_arm64", "windows_amd64"]


def metadata_version() -> str:
    data = tomllib.loads((ROOT / "duckdb-release.toml").read_text())
    return data["duckdb"]["version"]


def status_code(url: str) -> int:
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "agent-data-publication-verifier"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code


def fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "agent-data-publication-verifier"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def verify_install() -> None:
    import duckdb

    con = duckdb.connect()
    con.execute("INSTALL agent_data FROM community")
    con.execute("LOAD agent_data")
    con.execute("SELECT count(*) FROM duckdb_extensions() WHERE extension_name = 'agent_data'").fetchone()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duckdb-version", default=metadata_version())
    parser.add_argument("--platform", action="append", dest="platforms")
    parser.add_argument("--skip-install", action="store_true")
    args = parser.parse_args()

    platforms = args.platforms or DEFAULT_PLATFORMS
    failures: list[str] = []
    for platform in platforms:
        url = (
            "https://community-extensions.duckdb.org/"
            f"{args.duckdb_version}/{platform}/agent_data.duckdb_extension.gz"
        )
        code = status_code(url)
        print(f"{platform} {code} {url}")
        if code != 200:
            failures.append(f"{platform} binary returned {code}")

    list_url = "https://duckdb.org/community_extensions/list_of_extensions"
    list_body = fetch_text(list_url)
    in_list = "agent_data" in list_body
    print(f"aggregate_list_contains_agent_data={in_list}")
    if not in_list:
        failures.append("aggregate community extension list does not include agent_data")

    if not args.skip_install:
        try:
            verify_install()
            print("community_install=pass")
        except Exception as exc:
            failures.append(f"INSTALL/LOAD failed: {exc}")
            print(f"community_install=fail: {exc}")

    if failures:
        print("Publication verification failed. If this is a pull-request build, confirm whether upstream deploy logs say 'No AWS key found, skipping..'.", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
