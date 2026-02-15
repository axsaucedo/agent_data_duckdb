# agent_data — Marimo Explorer

Interactive [marimo](https://marimo.io) notebook for exploring AI coding agent session data using the [`agent_data`](https://community-extensions.duckdb.org/extensions/agent_data.html) DuckDB extension.

## Setup

```bash
uv init
uv venv --seed
echo ". .venv/bin/activate" > .envrc
direnv allow
uv sync
```

## Usage

```bash
marimo edit explore.py
```

The notebook auto-detects data from `~/.claude` and `~/.copilot`. Override via environment variables:

```bash
AGENT_DATA_PATH=~/custom/.claude COPILOT_DATA_PATH=~/custom/.copilot marimo edit explore.py
```

## Features

- Overview table with row counts by source
- Conversations breakdown by message type
- Session explorer with dropdown selector
- Todos status distribution
- Plans listing
- Command history with timestamps
- Daily activity stats
- Cross-source analysis with session aggregation
