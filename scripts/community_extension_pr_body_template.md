## Summary
- bumps `extensions/agent_data/description.yml` `repo.ref` to `{source_ref}`
- the new source ref targets DuckDB `{duckdb_version}`, `duckdb`/`libduckdb-sys` crate `{crate_version}`, and `extension-ci-tools` `{ci_tools_ref}`
- this should restore latest-stable community binaries so `agent_data` appears in the generated DuckDB community extension list again

## Validation in source repo
Source PR: {source_pr_url}

Local validation performed there:
- `cargo metadata --locked --format-version 1`
- `cargo check --locked`
- `make configure`
- `make debug`
- `make test`
- `cargo test --locked`
- `cd examples/tui && uv run pytest`
- manual DuckDB/Python smoke queries against `build/debug/agent_data.duckdb_extension` for Claude and Copilot synthetic data

## Current public baseline
- `https://duckdb.org/community_extensions/extensions/agent_data.html` returns 200
- `https://community-extensions.duckdb.org/{duckdb_version}/osx_arm64/agent_data.duckdb_extension.gz` returns 404 before trusted deployment
- aggregate list membership for `agent_data` is currently 0 before trusted deployment
- `INSTALL agent_data FROM community` currently fails on DuckDB {duckdb_python_version} before trusted deployment
