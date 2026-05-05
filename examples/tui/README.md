# Agent Chronicle TUI

Terminal-native explorer for AI coding agent session data, powered by the
[`agent_data`](https://community-extensions.duckdb.org/extensions/agent_data.html) DuckDB extension
and built with [Textual](https://textual.textualize.io/).

![Agent Chronicle TUI](../../docs/tui.gif)

## Features

- **Session Browser** — Filterable session table with event timeline and scrollable detail panel
- **Overview Dashboard** — Metrics, Unicode bar charts, and activity sparklines
- **SQL Query Editor** — Interactive editor with sample queries, `Enter` to execute
- **Keyboard-first** — Full vim-style navigation (`j`/`k`/`h`/`l`) with mouse support
- **Transparent dark theme** — Tokyo Night palette with terminal background transparency

## Quick Start

```bash
cd examples/tui
uv sync
uv run python -m agent_chronicle
```

Or with custom data paths:

```bash
uv run python -m agent_chronicle --claude-path ~/.claude --copilot-path ~/.copilot
```

Use a locally built extension during development or before community binaries
are available for a new DuckDB release:

```bash
AGENT_DATA_EXTENSION_PATH=../../build/debug/agent_data.duckdb_extension \
uv run python -m agent_chronicle
```

## Development

```bash
make install   # Install dependencies
make run       # Start TUI app
make dev       # Start with hot reload
make test      # Run tests (42 assertions)
```

## Keyboard Shortcuts

| Key | Context | Action |
|-----|---------|--------|
| `1` / `2` / `3` | Global | Switch tabs (Browser / Overview / SQL) |
| `?` | Global | Toggle help overlay |
| `q` | Global | Quit |
| `j` / `k` | Lists & panels | Cursor / scroll down / up |
| `l` / `Enter` | Browser | Drill into: sessions → timeline → detail |
| `h` / `Escape` | Browser | Drill back: detail → timeline → sessions |
| `/` | Browser | Focus filter input |
| `Enter` | SQL editor | Execute query |
| `s` | SQL (non-editor) | Toggle between query and sample views |

## Architecture

Built with Python Textual, reusing the data layer from the Streamlit explorer.
The app loads the `agent_data` DuckDB community extension, or the local path in
`AGENT_DATA_EXTENSION_PATH`, to read Claude and Copilot session data directly
from their local storage directories.

Data loading is async (threaded workers with per-thread DuckDB connections)
so the UI never blocks during startup or query execution.
