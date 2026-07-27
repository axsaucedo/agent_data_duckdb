#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

mkdir -p tmp

python3 scripts/update_duckdb_release.py --check-consistency

make clean_all
cargo metadata --locked > tmp/cargo-metadata.json
cargo check --locked
make configure
make debug
make test
cargo test --locked

# TUI example tests are informational only: the extension is validated by
# make test, cargo test, and the smoke test below. UI tests must not block
# a DuckDB release update.
if [ -f examples/tui/pyproject.toml ]; then
  if ! (
    cd examples/tui
    AGENT_DATA_EXTENSION_PATH="$ROOT/build/debug/agent_data.duckdb_extension" uv run pytest
  ); then
    echo "WARNING: TUI example tests failed (non-blocking for release validation)" >&2
  fi
fi

DUCKDB_PYTHON_VERSION="$(
  python3 - <<'PY'
import tomllib
with open("duckdb-release.toml", "rb") as f:
    print(tomllib.load(f)["duckdb"]["python_version"])
PY
)"

AGENT_DATA_EXTENSION_PATH="$ROOT/build/debug/agent_data.duckdb_extension" \
  uv run --with "duckdb==${DUCKDB_PYTHON_VERSION}" python scripts/smoke_duckdb_release.py \
  | tee tmp/manual-duckdb-${DUCKDB_PYTHON_VERSION}-smoke.log
