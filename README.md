# agent_data — DuckDB Extension for Agent Session Data

The DuckDB extension for Agent Software Development Data written in Rust.

**Supported frameworks:** Claude Code data (`~/.claude`) and GitHub Copilot CLI data (`~/.copilot`).

> OpenAI Codex & Gemini CLI coming soon™.

## Installing

```sql
INSTALL anndata FROM community;
LOAD anndata;
```

## Quick Start

```sql

-- Load all data from both Claude and Copilot
SELECT * FROM read_conversations(path='~/.claude')
UNION ALL
SELECT * FROM read_conversations(path='~/.copilot');


-- Query Claude Code data (auto-detected from folder structure)
FROM read_conversations(path='~/.claude');
FROM read_plans(path='~/.claude');
FROM read_todos(path='~/.claude');
FROM read_history(path='~/.claude');
FROM read_stats(path='~/.claude');

-- Query Copilot CLI data
FROM read_conversations(path='~/.copilot');
FROM read_plans(path='~/.copilot');
FROM read_history(path='~/.copilot');
FROM read_todos(path='~/.copilot');

-- Explicit source override
FROM read_conversations(path='some/path', source='copilot');
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
duckdb -unsigned -c "LOAD 'build/debug/agent_data.duckdb_extension'; FROM read_conversations(path='~/.claude');"
```

## API Reference

All functions accept:
- **`path`** (optional) — data directory path. Defaults to `~/.claude`. The provider is auto-detected from folder structure (`projects/` → Claude, `session-state/` → Copilot).
- **`source`** (optional) — explicit provider override: `'claude'` or `'copilot'`. Use when auto-detection fails or to force a specific parser.

Every table includes a **`source`** column (`'claude'` or `'copilot'`) as the first column.

### `read_conversations([path], [source])`

Reads conversation/event data.
- **Claude:** JSONL files from `projects/<project>/<session>.jsonl`
- **Copilot:** JSONL events from `session-state/<uuid>/events.jsonl`

| Column | Type | Description |
|--------|------|-------------|
| `source` | VARCHAR | `'claude'` or `'copilot'` |
| `session_id` | VARCHAR | Session UUID |
| `project_path` | VARCHAR | Project/working directory path |
| `project_dir` | VARCHAR | Raw encoded directory name (Claude only) |
| `file_name` | VARCHAR | Source filename |
| `is_agent` | BOOLEAN | Sub-agent conversation (Claude only) |
| `line_number` | BIGINT | Line number within file (1-based) |
| `message_type` | VARCHAR | See message type mappings below |
| `uuid` | VARCHAR | Message/event UUID |
| `parent_uuid` | VARCHAR | Parent message/event UUID |
| `timestamp` | VARCHAR | ISO 8601 timestamp |
| `message_role` | VARCHAR | `user`, `assistant`, `tool`, or NULL |
| `message_content` | VARCHAR | Text content |
| `model` | VARCHAR | AI model used |
| `tool_name` | VARCHAR | Tool called |
| `tool_use_id` | VARCHAR | Tool use/call identifier |
| `tool_input` | VARCHAR | Tool input as JSON string |
| `input_tokens` | BIGINT | Input token count (Claude per-message, Copilot truncation) |
| `output_tokens` | BIGINT | Output token count |
| `cache_creation_tokens` | BIGINT | Cache creation tokens (Claude only) |
| `cache_read_tokens` | BIGINT | Cache read tokens (Claude only) |
| `slug` | VARCHAR | Session slug (Claude only) |
| `git_branch` | VARCHAR | Git branch |
| `cwd` | VARCHAR | Working directory |
| `version` | VARCHAR | Agent CLI version |
| `stop_reason` | VARCHAR | Stop reason (Claude only) |
| `repository` | VARCHAR | GitHub repository (Copilot only) |

**Message type mappings:**

| Claude | Copilot | Description |
|--------|---------|-------------|
| `user` | `user` | User message |
| `assistant` | `assistant` | Assistant response |
| `system` | — | System prompt |
| `summary` | — | Conversation summary |
| — | `reasoning` | Assistant reasoning |
| — | `turn_start` / `turn_end` | Assistant turn boundaries |
| — | `tool_start` / `tool_result` | Tool execution events |
| — | `session_start` / `session_resume` | Session lifecycle |
| — | `session_info` / `session_error` | Session info/errors |
| — | `truncation` / `model_change` | Context management |
| — | `compaction_start` / `compaction_complete` | Context compaction |
| — | `abort` | User cancellation |

### `read_plans([path], [source])`

Reads plan files.
- **Claude:** `plans/*.md`
- **Copilot:** `session-state/<uuid>/plan.md`

| Column | Type | Description |
|--------|------|-------------|
| `source` | VARCHAR | `'claude'` or `'copilot'` |
| `session_id` | VARCHAR | Parent session UUID (Copilot only, NULL for Claude) |
| `plan_name` | VARCHAR | Plan name (filename stem or workspace summary) |
| `file_name` | VARCHAR | Full filename |
| `file_path` | VARCHAR | Absolute file path |
| `content` | VARCHAR | Full markdown content |
| `file_size` | BIGINT | File size in bytes |

### `read_todos([path], [source])`

Reads todo/checklist items.
- **Claude:** `todos/<session>-agent-<agent>.json`
- **Copilot:** Checkpoint markdown checklists from `session-state/<uuid>/checkpoints/*.md`

| Column | Type | Description |
|--------|------|-------------|
| `source` | VARCHAR | `'claude'` or `'copilot'` |
| `session_id` | VARCHAR | Parent session UUID |
| `agent_id` | VARCHAR | Agent UUID (Claude only, NULL for Copilot) |
| `file_name` | VARCHAR | Source filename |
| `item_index` | BIGINT | 0-based index (-1 for parse errors) |
| `content` | VARCHAR | Todo item text |
| `status` | VARCHAR | `pending`, `in_progress`, `completed`, or `_parse_error` |
| `active_form` | VARCHAR | Active form description (Claude only) |

### `read_history([path], [source])`

Reads command history.
- **Claude:** `history.jsonl` (structured JSONL)
- **Copilot:** `command-history-state.json` (simple string array)

| Column | Type | Description |
|--------|------|-------------|
| `source` | VARCHAR | `'claude'` or `'copilot'` |
| `line_number` | BIGINT | Line/entry number (1-based) |
| `timestamp_ms` | BIGINT | Unix timestamp in ms (Claude only) |
| `project` | VARCHAR | Project path (Claude only) |
| `session_id` | VARCHAR | Session UUID (Claude only) |
| `display` | VARCHAR | Command/prompt text |
| `pasted_contents` | VARCHAR | Pasted content as JSON (Claude only) |

### `read_stats([path], [source])`

Reads daily activity stats. Currently Claude only — returns empty for Copilot.

| Column | Type | Description |
|--------|------|-------------|
| `source` | VARCHAR | `'claude'` |
| `date` | VARCHAR | Date (YYYY-MM-DD) |
| `message_count` | BIGINT | Messages sent that day |
| `session_count` | BIGINT | Sessions started that day |
| `tool_call_count` | BIGINT | Tool calls made that day |

## Provider Detection

The extension auto-detects the data source by examining the directory structure:
- **Claude:** contains `projects/` directory
- **Copilot:** contains `session-state/` directory
- **Unknown:** returns empty results (or use `source` parameter to force)

```sql
-- Auto-detect
FROM read_conversations(path='~/.claude');   -- detected as Claude
FROM read_conversations(path='~/.copilot');  -- detected as Copilot

-- Override detection
FROM read_conversations(path='custom/dir', source='copilot');
```

## Join Keys

Tables can be joined within the same source:

```sql
-- Conversations ↔ History (via session_id)
SELECT c.*, h.display
FROM read_conversations(path='~/.claude') c
JOIN read_history(path='~/.claude') h ON c.session_id = h.session_id;

-- Cross-source: always filter by source
SELECT * FROM (
    SELECT * FROM read_conversations(path='~/.claude')
    UNION ALL
    SELECT * FROM read_conversations(path='~/.copilot')
) WHERE source = 'copilot';
```

| Join | Left Key | Right Key | Notes |
|------|----------|-----------|-------|
| conversations ↔ history | `session_id` | `session_id` | Same source only |
| conversations ↔ todos | `session_id` | `session_id` | Same source only |
| conversations ↔ plans | `slug` | `plan_name` | Claude only |
| conversations ↔ history | `project_path` | `project` | Claude only |

## Parse Error Policy

When a JSONL line or JSON file cannot be parsed, the extension emits a row with:
- `message_type = '_parse_error'` (conversations)
- `status = '_parse_error'` (todos)
- `display = 'Parse error: ...'` (history)

Filter them with `WHERE message_type != '_parse_error'`.

## Testing

```bash
# Build and run all 100+ assertion-driven tests + Python smoke test
make test
```

The test suite covers:
- Row count invariants for all 5 functions × 2 sources
- Column validation (NULLs, formats, value ranges)
- Cross-source UNION queries and source isolation
- Provider auto-detection and explicit source override
- Cross-table join correctness
- Parse error detection
- Basic benchmark checks

Test data:
- `test/data/` — Synthetic Claude data (3 projects, 6 sessions, 180 conversations)
- `test/data_copilot/` — Synthetic Copilot data (4 sessions, 53 events, all 16 event types)

## Examples (Marimo Notebooks)

```bash
# Run with test data (default)
marimo run examples/explore.py

# Run with your own data
AGENT_DATA_PATH=~/.claude COPILOT_DATA_PATH=~/.copilot marimo run examples/explore.py
```

The notebook loads both sources via UNION ALL and provides:
- Overview dashboard with row counts by source
- Message type distribution by source
- Session explorer with source prefix
- Todo status by source
- Cross-source session activity summary

## Architecture

The extension uses a **generic VTab framework** (`vtab.rs`) with provider auto-detection:

```
src/
├── lib.rs              # Entry point (registers 5 functions)
├── vtab.rs             # Generic VTab framework (TableFunc trait)
├── detect.rs           # Provider enum + auto-detection logic
├── types/
│   ├── mod.rs          # Re-exports
│   ├── claude.rs       # Claude JSON/JSONL serde types
│   └── copilot.rs      # Copilot event serde types
├── utils.rs            # Path resolution, file discovery (both providers)
├── conversations.rs    # Unified conversations (Claude + Copilot)
├── plans.rs            # Unified plans
├── todos.rs            # Unified todos
├── history.rs          # Unified history
└── stats.rs            # Stats (Claude only)
```

Each module implements the `TableFunc` trait:
1. **`columns()`** — column definitions
2. **`load_rows(path, source)`** — auto-detect provider, dispatch to Claude or Copilot loader
3. **`write_row(output, idx, row)`** — write one row to DuckDB vectors

## License

See LICENSE file for details.
