#!/usr/bin/env python3
"""Check or update DuckDB release targets across the repository."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
import urllib.request
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
METADATA = ROOT / "duckdb-release.toml"
EXTENSION_WORKFLOW = ROOT / ".github" / "workflows" / "MainDistributionPipeline.yml"
EXAMPLE_PYPROJECTS = [
    ROOT / "examples" / "explorer" / "pyproject.toml",
    ROOT / "examples" / "marimo" / "pyproject.toml",
    ROOT / "examples" / "tui" / "pyproject.toml",
]


@dataclass(frozen=True)
class ReleaseTarget:
    duckdb_version: str
    python_version: str
    crate_version: str
    ci_tools_ref: str
    excluded_archs: str


def http_json(url: str) -> object:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "agent-data-duckdb-release-updater",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def latest_duckdb_release() -> str:
    data = http_json("https://api.github.com/repos/duckdb/duckdb/releases/latest")
    tag = data.get("tag_name") if isinstance(data, dict) else None
    if not isinstance(tag, str) or not re.fullmatch(r"v\d+\.\d+\.\d+", tag):
        raise RuntimeError(f"Could not determine latest DuckDB release from GitHub: {tag!r}")
    return tag


def crate_versions(crate: str) -> set[str]:
    data = http_json(f"https://crates.io/api/v1/crates/{crate}")
    versions = data.get("versions") if isinstance(data, dict) else None
    if not isinstance(versions, list):
        raise RuntimeError(f"Could not read versions for crate {crate}")
    return {item["num"] for item in versions if isinstance(item, dict) and "num" in item}


def duckdb_version_parts(duckdb_version: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", duckdb_version)
    if not match:
        raise ValueError(f"DuckDB version must look like vX.Y.Z, got {duckdb_version!r}")
    return tuple(int(part) for part in match.groups())


def candidate_crate_versions(duckdb_version: str) -> list[str]:
    major, minor, patch = duckdb_version_parts(duckdb_version)
    normal = f"{major}.{minor}.{patch}"
    # duckdb-rs uses 1.10XYZ.0 for DuckDB 1.5+ releases.
    encoded = f"{major}.{10000 + (minor * 100) + patch}.0"
    return list(dict.fromkeys([encoded, normal]))


def resolve_crate_version(duckdb_version: str) -> str:
    duckdb_versions = crate_versions("duckdb")
    sys_versions = crate_versions("libduckdb-sys")
    for candidate in candidate_crate_versions(duckdb_version):
        if candidate in duckdb_versions and candidate in sys_versions:
            return candidate
    candidates = ", ".join(candidate_crate_versions(duckdb_version))
    raise RuntimeError(
        "Could not resolve matching duckdb/libduckdb-sys crates for "
        f"{duckdb_version}; tried {candidates}"
    )


def extension_ci_heads() -> list[str]:
    data = http_json("https://api.github.com/repos/duckdb/extension-ci-tools/git/matching-refs/heads/")
    if not isinstance(data, list):
        raise RuntimeError("Could not read extension-ci-tools branch refs")
    refs: list[str] = []
    for item in data:
        ref = item.get("ref") if isinstance(item, dict) else None
        if isinstance(ref, str) and ref.startswith("refs/heads/"):
            refs.append(ref.removeprefix("refs/heads/"))
    return refs


def resolve_ci_tools_ref(duckdb_version: str) -> str:
    major, minor, _ = duckdb_version_parts(duckdb_version)
    heads = extension_ci_heads()
    minor_prefix = f"v{major}.{minor}-"
    codename_heads = sorted(head for head in heads if head.startswith(minor_prefix))
    if codename_heads:
        return codename_heads[-1]
    exact_heads = [duckdb_version, f"v{major}.{minor}.0", f"v{major}.{minor}"]
    for head in exact_heads:
        if head in heads:
            return head
    raise RuntimeError(f"Could not resolve extension-ci-tools ref for {duckdb_version}")


def read_metadata() -> ReleaseTarget:
    data = tomllib.loads(METADATA.read_text())
    return ReleaseTarget(
        duckdb_version=data["duckdb"]["version"],
        python_version=data["duckdb"]["python_version"],
        crate_version=data["duckdb"]["crate_version"],
        ci_tools_ref=data["ci"]["tools_ref"],
        excluded_archs=data["ci"]["excluded_archs"],
    )


def write_metadata(target: ReleaseTarget) -> None:
    METADATA.write_text(
        "\n".join(
            [
                "[duckdb]",
                f'version = "{target.duckdb_version}"',
                f'python_version = "{target.python_version}"',
                f'crate_version = "{target.crate_version}"',
                "",
                "[ci]",
                f'tools_ref = "{target.ci_tools_ref}"',
                f'excluded_archs = "{target.excluded_archs}"',
                "",
            ]
        )
    )


def replace(path: Path, pattern: str, replacement: str) -> None:
    text = path.read_text()
    new_text, count = re.subn(pattern, replacement, text, flags=re.MULTILINE)
    if count == 0:
        raise RuntimeError(f"No match for {pattern!r} in {path}")
    path.write_text(new_text)


def apply_target(target: ReleaseTarget, update_lockfile: bool) -> None:
    write_metadata(target)
    replace(
        ROOT / "Cargo.toml",
        r'duckdb = \{ version = "=[^"]+", features = \["loadable-extension"\] \}',
        f'duckdb = {{ version = "={target.crate_version}", features = ["loadable-extension"] }}',
    )
    replace(
        ROOT / "Cargo.toml",
        r'libduckdb-sys = "=[^"]+"',
        f'libduckdb-sys = "={target.crate_version}"',
    )
    replace(
        ROOT / "Makefile",
        r"^TARGET_DUCKDB_VERSION=.*$",
        f"TARGET_DUCKDB_VERSION={target.duckdb_version}",
    )
    replace(
        EXTENSION_WORKFLOW,
        r"uses: duckdb/extension-ci-tools/\.github/workflows/_extension_distribution\.yml@.+",
        f"uses: duckdb/extension-ci-tools/.github/workflows/_extension_distribution.yml@{target.ci_tools_ref}",
    )
    replace(
        EXTENSION_WORKFLOW,
        r"duckdb_version: .+",
        f"duckdb_version: {target.duckdb_version}",
    )
    replace(
        EXTENSION_WORKFLOW,
        r"ci_tools_version: .+",
        f"ci_tools_version: {target.ci_tools_ref}",
    )
    replace(
        EXTENSION_WORKFLOW,
        r'exclude_archs: ".+"',
        f'exclude_archs: "{target.excluded_archs}"',
    )
    for pyproject in EXAMPLE_PYPROJECTS:
        replace(pyproject, r'duckdb>=\d+\.\d+\.\d+', f"duckdb>={target.python_version}")
    if update_lockfile:
        run(["cargo", "update", "-p", "duckdb", "--precise", target.crate_version])
        run(["cargo", "update", "-p", "libduckdb-sys", "--precise", target.crate_version])


def run(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def parse_current_files() -> dict[str, str]:
    cargo = (ROOT / "Cargo.toml").read_text()
    makefile = (ROOT / "Makefile").read_text()
    workflow = EXTENSION_WORKFLOW.read_text()
    current = {
        "metadata.duckdb_version": read_metadata().duckdb_version,
        "metadata.python_version": read_metadata().python_version,
        "metadata.crate_version": read_metadata().crate_version,
        "metadata.ci_tools_ref": read_metadata().ci_tools_ref,
        "metadata.excluded_archs": read_metadata().excluded_archs,
        "cargo.duckdb": match_one(r'duckdb = \{ version = "=([^"]+)"', cargo, "Cargo.toml duckdb"),
        "cargo.libduckdb-sys": match_one(r'libduckdb-sys = "=([^"]+)"', cargo, "Cargo.toml libduckdb-sys"),
        "makefile.duckdb_version": match_one(r"^TARGET_DUCKDB_VERSION=(.+)$", makefile, "Makefile"),
        "workflow.ci_tools_ref": match_one(
            r"uses: duckdb/extension-ci-tools/\.github/workflows/_extension_distribution\.yml@(.+)",
            workflow,
            "workflow reusable ref",
        ),
        "workflow.duckdb_version": match_one(r"duckdb_version: (.+)", workflow, "workflow duckdb_version"),
        "workflow.ci_tools_version": match_one(r"ci_tools_version: (.+)", workflow, "workflow ci_tools_version"),
        "workflow.excluded_archs": match_one(r'exclude_archs: "(.+)"', workflow, "workflow exclude_archs"),
    }
    for pyproject in EXAMPLE_PYPROJECTS:
        current[f"{pyproject.relative_to(ROOT)}.duckdb"] = match_one(
            r"duckdb>=(\d+\.\d+\.\d+)", pyproject.read_text(), str(pyproject)
        )
    return current


def match_one(pattern: str, text: str, label: str) -> str:
    match = re.search(pattern, text, flags=re.MULTILINE)
    if not match:
        raise RuntimeError(f"Could not parse {label}")
    return match.group(1).strip()


def expected_values(target: ReleaseTarget) -> dict[str, str]:
    expected = {
        "metadata.duckdb_version": target.duckdb_version,
        "metadata.python_version": target.python_version,
        "metadata.crate_version": target.crate_version,
        "metadata.ci_tools_ref": target.ci_tools_ref,
        "metadata.excluded_archs": target.excluded_archs,
        "cargo.duckdb": target.crate_version,
        "cargo.libduckdb-sys": target.crate_version,
        "makefile.duckdb_version": target.duckdb_version,
        "workflow.ci_tools_ref": target.ci_tools_ref,
        "workflow.duckdb_version": target.duckdb_version,
        "workflow.ci_tools_version": target.ci_tools_ref,
        "workflow.excluded_archs": target.excluded_archs,
    }
    for pyproject in EXAMPLE_PYPROJECTS:
        expected[f"{pyproject.relative_to(ROOT)}.duckdb"] = target.python_version
    return expected


def check_target(target: ReleaseTarget) -> list[str]:
    current = parse_current_files()
    expected = expected_values(target)
    mismatches: list[str] = []
    for key, expected_value in expected.items():
        current_value = current.get(key)
        if current_value != expected_value:
            mismatches.append(f"{key}: current={current_value!r} expected={expected_value!r}")
    return mismatches


def resolve_target(duckdb_version: str | None) -> ReleaseTarget:
    version = duckdb_version or latest_duckdb_release()
    bare_version = version.removeprefix("v")
    return ReleaseTarget(
        duckdb_version=version,
        python_version=bare_version,
        crate_version=resolve_crate_version(version),
        ci_tools_ref=resolve_ci_tools_ref(version),
        excluded_archs=read_metadata().excluded_archs if METADATA.exists() else "wasm_mvp;wasm_eh;wasm_threads;linux_amd64_musl",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duckdb-version", help="DuckDB version to check/apply, e.g. v1.5.2")
    parser.add_argument("--check", action="store_true", help="Check configured versions for drift")
    parser.add_argument("--apply", action="store_true", help="Apply the resolved version to local files")
    parser.add_argument(
        "--no-lockfile-update",
        action="store_true",
        help="Do not run cargo update after editing Cargo.toml",
    )
    args = parser.parse_args()
    if args.check == args.apply:
        parser.error("choose exactly one of --check or --apply")

    target = resolve_target(args.duckdb_version)
    if args.apply:
        apply_target(target, update_lockfile=not args.no_lockfile_update)

    mismatches = check_target(target)
    if mismatches:
        print(f"DuckDB release drift detected for {target.duckdb_version}:")
        for mismatch in mismatches:
            print(f"- {mismatch}")
        return 1

    print(
        "DuckDB release configuration is current: "
        f"{target.duckdb_version} / crate {target.crate_version} / CI {target.ci_tools_ref}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
