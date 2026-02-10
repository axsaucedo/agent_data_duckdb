# agent_data — DuckDB Extension for Agent Session Data

A DuckDB extension that reads and queries agent/copilot session data as structured tables. Built in Rust using the official DuckDB extension template.

**Current scope:** Claude Code (`~/.claude`) data only. Designed to expand to other agents (Codex, GitHub Copilot) in the future.

## Quick Start

```sql
-- Load the extension
LOAD 'build/debug/agent_data.duckdb_extension';

-- Query your Claude Code data (defaults to ~/.claude)
FROM read_conversations();
FROM read_plans();
FROM read_todos();
FROM read_history();
FROM read_stats();

-- Or specify a path
FROM read_conversations(path='test/data');
```

## Installation

### Prerequisites

- Rust toolchain (edition 2021+)
- DuckDB 1.4.4
- Python 3.12+ (for build tooling and notebooks)

### Build

```bash
# First time: configure build environment
make configure

# Build debug extension
make debug

# Build release extension
make release

# Run tests
make test
```

The compiled extension is at `build/debug/agent_data.duckdb_extension` (or `build/release/`).

### Load in DuckDB

```bash
duckdb -unsigned -c "LOAD 'build/debug/agent_data.duckdb_extension'; FROM read_conversations();"
```

## API Reference

All functions accept an optional `path` parameter. When omitted, they default to `~/.claude`.

```sql
-- Both forms work:
FROM read_conversations();              -- defaults to ~/.claude
FROM read_conversations(path='test/data');  -- explicit path
```

### `read_conversations([path])`

Reads JSONL conversation files from `projects/<project>/<session>.jsonl`.

| Column | Type | Description |
|--------|------|-------------|
| `session_id` | VARCHAR | Session UUID (from message data or filename) |
| `project_path` | VARCHAR | Canonical project path (from `cwd` field, matches `history.project`) |
| `project_dir` | VARCHAR | Raw encoded directory name (e.g., `-Users-user-project`) |
| `file_name` | VARCHAR | JSONL filename |
| `is_agent` | BOOLEAN | True for sub-agent conversations (`agent-*.jsonl`) |
| `line_number` | BIGINT | Line number within the file (1-based, per-file) |
| `message_type` | VARCHAR | `user`, `assistant`, `system`, `summary`, `file-history-snapshot`, `queue-operation`, `_parse_error` |
| `uuid` | VARCHAR | Message UUID |
| `parent_uuid` | VARCHAR | Parent message UUID (for threading) |
| `timestamp` | VARCHAR | ISO 8601 timestamp |
| `message_role` | VARCHAR | `user` or `assistant` |
| `message_content` | VARCHAR | Text content of the message |
| `model` | VARCHAR | AI model used (assistant messages) |
| `tool_name` | VARCHAR | Tool called (assistant messages) |
| `tool_use_id` | VARCHAR | Tool use identifier |
| `tool_input` | VARCHAR | Tool input as JSON string |
| `input_tokens` | BIGINT | Input token count |
| `output_tokens` | BIGINT | Output token count |
| `cache_creation_tokens` | BIGINT | Cache creation tokens |
| `cache_read_tokens` | BIGINT | Cache read tokens |
| `slug` | VARCHAR | Session slug (can join with plan names) |
| `git_branch` | VARCHAR | Git branch at time of message |
| `cwd` | VARCHAR | Working directory |
| `version` | VARCHAR | Claude Code version |
| `stop_reason` | VARCHAR | Stop reason (assistant messages) |

### `read_plans([path])`

Reads markdown plan files from `plans/*.md`.

| Column | Type | Description |
|--------|------|-------------|
| `plan_name` | VARCHAR | Plan name (filename stem) |
| `file_name` | VARCHAR | Full filename with extension |
| `file_path` | VARCHAR | Absolute file path |
| `content` | VARCHAR | Full markdown content |
| `file_size` | BIGINT | File size in bytes |

### `read_todos([path])`

Reads JSON todo files from `todos/<session>-agent-<agent>.json`.

| Column | Type | Description |
|--------|------|-------------|
| `session_id` | VARCHAR | Parent session UUID |
| `agent_id` | VARCHAR | Agent UUID |
| `file_name` | VARCHAR | Source filename |
| `item_index` | BIGINT | 0-based index within the file (-1 for parse errors) |
| `content` | VARCHAR | Todo item text |
| `status` | VARCHAR | `pending`, `in_progress`, `completed`, or `_parse_error` |
| `active_form` | VARCHAR | Active form description |

### `read_history([path])`

Reads the global command history from `history.jsonl`.

| Column | Type | Description |
|--------|------|-------------|
| `line_number` | BIGINT | Line number (1-based) |
| `timestamp_ms` | BIGINT | Unix timestamp in milliseconds |
| `project` | VARCHAR | Project path (matches `conversations.project_path`) |
| `session_id` | VARCHAR | Session UUID |
| `display` | VARCHAR | Command/prompt display text |
| `pasted_contents` | VARCHAR | Pasted content as JSON |

### `read_stats([path])`

Reads the daily activity stats from `stats-cache.json`.

| Column | Type | Description |
|--------|------|-------------|
| `date` | VARCHAR | Date (YYYY-MM-DD) |
| `message_count` | BIGINT | Messages sent that day |
| `session_count` | BIGINT | Sessions started that day |
| `tool_call_count` | BIGINT | Tool calls made that day |

## Join Keys

The tables are designed to be joined together:

```sql
-- Conversations ↔ History (via session_id)
SELECT c.*, h.display
FROM read_conversations() c
JOIN read_history() h ON c.session_id = h.session_id;

-- Conversations ↔ History (via project_path)
SELECT c.project_path, COUNT(*) as msgs, COUNT(DISTINCT h.display) as cmds
FROM read_conversations() c
JOIN read_history() h ON c.project_path = h.project
GROUP BY c.project_path;

-- Conversations ↔ Todos (via session_id)
SELECT c.session_id, t.content, t.status
FROM read_conversations() c
JOIN read_todos() t ON c.session_id = t.session_id;

-- Conversations ↔ Plans (via slug = plan_name)
SELECT c.session_id, p.plan_name, p.content
FROM read_conversations() c
JOIN read_plans() p ON c.slug = p.plan_name;
```

| Join | Left Key | Right Key | Notes |
|------|----------|-----------|-------|
| conversations ↔ history | `session_id` | `session_id` | Primary join |
| conversations ↔ history | `project_path` | `project` | Project-level join |
| conversations ↔ todos | `session_id` | `session_id` | Session-level |
| conversations ↔ plans | `slug` | `plan_name` | Matches when plan was created in session |

## Parse Error Policy

When a JSONL line or JSON file cannot be parsed, the extension emits a row with:
- `message_type = '_parse_error'` (conversations)
- `status = '_parse_error'` (todos)
- `display = 'Parse error: ...'` (history)

This ensures no data is silently dropped. Filter them with:

```sql
SELECT * FROM read_conversations(path='test/data') WHERE message_type != '_parse_error';
```

## Testing

```bash
# Build and run all 50+ assertion-driven tests
make test

# Or run tests directly
./scripts/test.sh
```

The test suite covers:
- Row count invariants for all 5 functions
- Column validation (NULLs, formats, value ranges)
- Cross-table join correctness
- Parse error detection
- Basic benchmark checks (timing threshold)

Test data is in `test/data/` — a synthetic Claude Code data directory with 3 projects, 6 sessions, agent conversations, plans, todos, history, and stats.

## Examples (Marimo Notebooks)

Interactive exploration notebooks are in `examples/`.

```bash
# Run with test data (default)
marimo run examples/explore.py

# Run with your own data
AGENT_DATA_PATH=~/.claude marimo run examples/explore.py

# Edit the notebook interactively
marimo edit examples/explore.py
```

The notebook includes:
- Overview dashboard with row counts
- Per-project message breakdown
- Session explorer with message details
- Todo status distribution
- Plan listing
- Command history timeline
- Cross-table analysis (sessions ↔ todos ↔ history)

## Project Structure

```
├── Cargo.toml          # Rust crate configuration
├── Makefile            # Build system (wraps extension-ci-tools)
├── src/
│   ├── lib.rs          # Extension entry point
│   ├── types.rs        # Serde types for JSON/JSONL
│   ├── utils.rs        # Path resolution, file discovery
│   ├── conversations.rs # read_conversations() implementation
│   ├── plans.rs        # read_plans() implementation
│   ├── todos.rs        # read_todos() implementation
│   ├── history.rs      # read_history() implementation
│   └── stats.rs        # read_stats() implementation
├── test/
│   ├── data/           # Synthetic test data (mock ~/.claude)
│   └── sql/            # SQL test files (assertion-driven)
├── scripts/
│   └── test.sh         # Test runner
├── examples/
│   └── explore.py      # Marimo notebook for exploration
└── docs/               # Additional documentation
```

## License

See LICENSE file for details.
