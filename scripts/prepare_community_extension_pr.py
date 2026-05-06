#!/usr/bin/env python3
"""Prepare a duckdb/community-extensions descriptor update for agent_data."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMMUNITY_REPO = ROOT / "tmp" / "community-extensions"
DESCRIPTOR = Path("extensions/agent_data/description.yml")
DEFAULT_BODY_TEMPLATE = ROOT / "scripts" / "community_extension_pr_body_template.md"


def run(command: list[str], cwd: Path = ROOT, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(command), flush=True)
    return subprocess.run(command, cwd=cwd, check=check, text=True, capture_output=False)


def output(command: list[str], cwd: Path = ROOT) -> str:
    return subprocess.check_output(command, cwd=cwd, text=True).strip()


def optional_output(command: list[str], cwd: Path = ROOT) -> str | None:
    try:
        return output(command, cwd=cwd)
    except subprocess.CalledProcessError:
        return None


def ensure_clean_source() -> None:
    status = output(["git", "status", "--porcelain"])
    ignored = {"?? .github/workflows/roborev.yml"}
    unexpected = [line for line in status.splitlines() if line and line not in ignored]
    if unexpected:
        raise RuntimeError("Source repository has uncommitted changes:\n" + "\n".join(unexpected))


def update_descriptor(path: Path, source_ref: str) -> None:
    lines = path.read_text().splitlines()
    in_repo = False
    changed = False
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if line == "repo:":
            in_repo = True
            new_lines.append(line)
            continue
        if in_repo and line and not line.startswith(" "):
            in_repo = False
        if in_repo and stripped.startswith("ref:"):
            indent = line[: len(line) - len(line.lstrip())]
            new_lines.append(f"{indent}ref: {source_ref}")
            changed = True
        else:
            new_lines.append(line)
    if not changed:
        raise RuntimeError(f"Could not find repo.ref in {path}")
    path.write_text("\n".join(new_lines) + "\n")


def release_metadata() -> dict[str, str]:
    with open(ROOT / "duckdb-release.toml", "rb") as handle:
        data = tomllib.load(handle)
    return {
        "duckdb_version": data["duckdb"]["version"],
        "duckdb_python_version": data["duckdb"]["python_version"],
        "crate_version": data["duckdb"]["crate_version"],
        "ci_tools_ref": data["ci"]["tools_ref"],
    }


def source_pr_url(explicit_url: str | None) -> str:
    if explicit_url:
        return explicit_url
    detected = optional_output(["gh", "pr", "view", "--json", "url", "--jq", ".url"])
    return detected or "TODO: add source PR URL"


def render_body(template: Path, source_ref: str, explicit_source_pr_url: str | None) -> str:
    values = release_metadata()
    values["source_ref"] = source_ref
    values["source_pr_url"] = source_pr_url(explicit_source_pr_url)
    return template.read_text().format(**values)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--community-repo", type=Path, default=DEFAULT_COMMUNITY_REPO)
    parser.add_argument("--source-ref", default=None, help="Source commit/tag to write; defaults to HEAD SHA")
    parser.add_argument("--branch", default="bump-agent-data-duckdb-release")
    parser.add_argument("--body-template", type=Path, default=DEFAULT_BODY_TEMPLATE)
    parser.add_argument("--source-pr-url", help="Source repository PR URL to include in the upstream PR body")
    parser.add_argument("--print-body", action="store_true", help="Render the upstream PR body and exit")
    parser.add_argument("--open-pr", action="store_true", help="Open a PR with gh after committing")
    parser.add_argument("--skip-clean-check", action="store_true")
    args = parser.parse_args()

    source_ref = args.source_ref or output(["git", "rev-parse", "HEAD"])
    body = render_body(args.body_template, source_ref, args.source_pr_url)
    if args.print_body:
        print(body)
        return 0

    if not args.skip_clean_check:
        ensure_clean_source()

    community_repo = args.community_repo.resolve()
    if not community_repo.exists():
        run(["git", "clone", "https://github.com/duckdb/community-extensions.git", str(community_repo)])

    descriptor = community_repo / DESCRIPTOR
    if not descriptor.exists():
        raise RuntimeError(f"Missing descriptor: {descriptor}")

    run(["git", "fetch", "origin", "main"], cwd=community_repo)
    run(["git", "checkout", "-B", args.branch, "origin/main"], cwd=community_repo)
    update_descriptor(descriptor, source_ref)
    run(["git", "add", str(DESCRIPTOR)], cwd=community_repo)
    diff = output(["git", "diff", "--cached", "--stat"], cwd=community_repo)
    if not diff:
        print("Descriptor already points at requested ref.")
        return 0
    run(["git", "commit", "-m", f"agent_data: update source ref to {source_ref[:12]}"], cwd=community_repo)

    if args.open_pr:
        run(["git", "push", "-u", "origin", args.branch], cwd=community_repo)
        run(
            [
                "gh",
                "pr",
                "create",
                "--repo",
                "duckdb/community-extensions",
                "--title",
                "agent_data: update source ref",
                "--body",
                body,
            ],
            cwd=community_repo,
        )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
