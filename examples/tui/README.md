# Agent Chronicle TUI

Terminal-native explorer for AI coding agent session data, powered by the
[`agent_data`](https://community-extensions.duckdb.org/extensions/agent_data.html) DuckDB extension
and built with [Textual](https://textual.textualize.io/).

## Features

- **Overview Dashboard** — Session/message metrics and activity stats
- **Session Browser** — Filterable session table with event timeline and detail panel
- **SQL Query Editor** — Interactive SQL editor with sample queries and results table
- **Keyboard-first** — Full keyboard navigation with mouse support
- **Dark theme** — Slate dark theme with color-coded message type badges

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

## Development

```bash
make install   # Install dependencies
make run       # Start TUI app
make dev       # Start with hot reload
make test      # Run tests
```

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `1` / `2` / `3` | Switch tabs (Overview / Browser / SQL) |
| `Tab` | Next tab |
| `Shift+Tab` | Previous tab |
| `?` | Toggle help overlay |
| `q` | Quit |
| `Enter` | Select / Open |
| `Escape` | Go back |
| `F5` | Execute SQL query |

## Architecture

Built with Python Textual, reusing the data layer from the Streamlit explorer.
The app loads the `agent_data` DuckDB community extension to read Claude and
Copilot session data directly from their local storage directories.
