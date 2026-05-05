# agent_data — Streamlit Explorer

A multi-page [Streamlit](https://streamlit.io) application for interactive exploration
of AI coding agent session data using the
[`agent_data`](https://community-extensions.duckdb.org/extensions/agent_data.html)
DuckDB extension.

![](../../docs/streamlit.gif)

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
streamlit run app.py
```

Override data paths via environment variables:

```bash
AGENT_DATA_CLAUDE_PATH=~/custom/.claude \
AGENT_DATA_COPILOT_PATH=~/custom/.copilot \
streamlit run app.py
```

Use a locally built extension during development or before community binaries
are available for a new DuckDB release:

```bash
AGENT_DATA_EXTENSION_PATH=../../build/debug/agent_data.duckdb_extension \
streamlit run app.py
```
