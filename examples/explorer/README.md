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

## Pages

### 📋 Session Browser

Chronicle-style session explorer:

- **Session list** with filtering by source, project, model, and minimum message count
- **Session detail** view with conversation timeline
- **Message detail** panel showing full content and metadata (UUIDs, tokens, stop reason)
- **Tool usage** breakdown per session (bar chart)
- **Session metadata** (slug, git branch, cwd, version)

### 🔎 SQL Query

Power-user SQL interface:

- **Free-form SQL editor** — write any query using agent_data functions
- **Sample queries** — categorized templates (Overview, Tool Analysis, Conversations, Todos & Plans, History, Joins)
- **Query builder** — pick table, columns, WHERE clause, ORDER BY, and LIMIT
- **CSV export** — download query results
- **Quick reference** — inline docs for all functions, parameters, and join keys

## Architecture

```
explorer/
├── app.py                       # Main entry & home page
├── db.py                        # Shared DuckDB connection
├── pages/
│   ├── 1_Session_Browser.py     # Chronicle-style session explorer
│   └── 2_SQL_Query.py           # SQL query interface
├── pyproject.toml               # Dependencies (streamlit, duckdb, pandas)
└── README.md
```
