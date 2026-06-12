# agent_data — DuckDB Extension for AI Agent Session Data

A [DuckDB extension](https://duckdb.org/community_extensions/list_of_extensions) written in Rust for querying, analysing and inspecting AI coding agents history. Read conversations, plans, todos, history, and usage stats directly from your local agent data directories.

**Supported agents:** [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (`~/.claude`) and [GitHub Copilot CLI](https://docs.github.com/en/copilot/github-copilot-in-the-cli) (`~/.copilot`).

> OpenAI Codex and Gemini CLI Coming Soon™.

Written in 🦀 Rust.

## Quickstart

<table>
<tr>
<td>

<h4> Load Extension </h4>

<pre><code class="language-sql">INSTALL agent_data FROM community;
LOAD agent_data;
</code></pre>

<h4> Run Query</h4>

<pre><code class="language-sql">SELECT c.*, h.display
FROM read_conversations(path='~/.claude') c
JOIN read_history(path='~/.claude') h
ON c.session_id = h.session_id;
</code></pre>

</td>
<td>

<h4>Or try the <a href="https://github.com/axsaucedo/agent_data_duckdb/tree/main/examples/explorer">Streamlit Example</a></h4>

<a href="https://github.com/axsaucedo/agent_data_duckdb/tree/main/examples/explorer">
<img src="docs/streamlit.gif">
</a>

<h4>Or the <a href="https://github.com/axsaucedo/agent_data_duckdb/tree/main/examples/tui">Terminal TUI</a></h4>

<a href="https://github.com/axsaucedo/agent_data_duckdb/tree/main/examples/tui">
<img src="docs/tui.gif">
</a>

</td>
</tr>
</table>

## Overview

All functions read from the default agent directory (`~/.claude` for Claude Code, `~/.copilot` for Copilot) when no `path` is provided. 

The provider is **auto-detected** from the directory structure.

```sql
-- How many conversations have I had with Claude?
SELECT COUNT(DISTINCT session_id) AS sessions,
       COUNT(*) AS total_messages
FROM read_conversations();

-- What did I work on this week?
SELECT date, message_count, tool_call_count
FROM read_stats()
ORDER BY date DESC
LIMIT 7;

-- Which tools does github copilot use most?
SELECT tool_name, COUNT(*) AS uses
FROM read_conversations('~/.copilot')
WHERE tool_name IS NOT NULL
GROUP BY tool_name
ORDER BY uses DESC
LIMIT 10;

-- What are my active todos in my custom claude path?
SELECT content, status
FROM read_todos('~/work_folder/.claude')
WHERE status != 'completed'
ORDER BY item_index;

-- Compare activity across Claude and Copilot
SELECT source, COUNT(DISTINCT session_id) AS sessions, COUNT(*) AS messages
FROM (
    SELECT * FROM read_conversations(path='~/.claude')
    UNION ALL
    SELECT * FROM read_conversations(path='~/.copilot')
)
GROUP BY source;
```

### Default Behavior

When called **without arguments**, each function reads from its provider's default path:

| Function | Default path | Detected as |
|----------|-------------|-------------|
| `read_conversations()` | `~/.claude` | Claude Code |
| `read_plans()` | `~/.claude` | Claude Code |
| `read_todos()` | `~/.claude` | Claude Code |
| `read_history()` | `~/.claude` | Claude Code |
| `read_stats()` | `~/.claude` | Claude Code |

To read Copilot data, pass the path explicitly:

```sql
FROM read_conversations(path='~/.copilot');
```

### Available Functions

All functions accept two optional parameters:
- **`path`** — data directory path (default: `~/.claude`). Auto-detected from folder structure (`projects/` → Claude, `session-state/` → Copilot).
- **`source`** — explicit provider override: `'claude'` or `'copilot'`. Use when auto-detection fails or for non-standard directory layouts.

Every table includes a **`source`** column (`'claude'` or `'copilot'`) as the first column.

### `read_conversations([path (opt)], [source (opt)])`

Reads conversation/event data.
- **Claude:** JSONL files from `projects/<project>/<session>.jsonl` (including nested sub-agent transcripts at `projects/<project>/<session>/subagents/agent-*.jsonl`)
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

## Examples

### Terminal TUI (Agent Chronicle)

Keyboard-driven terminal explorer with session browser, overview dashboard, and SQL editor:

```bash
cd examples/tui
uv sync
uv run python -m agent_chronicle
```

See [examples/tui/README.md](examples/tui/README.md) for details.

### Marimo Notebook

Interactive notebook for exploring agent data:

```bash
cd examples/marimo
uv sync
marimo edit explore.py
```

### Streamlit Explorer

Multi-page web application with session browser and SQL query interface:

```bash
cd examples/explorer
uv sync
streamlit run app.py
```

See [examples/explorer/README.md](examples/explorer/README.md) for details.

## Testing

```bash
# Build and run all SQLLogicTest assertions
make test
```

207 pinned assertions across 14 test files covering row counts, column validation, cross-source queries, join invariants, edge cases, and parse error handling.

## Building from Source

```bash
# First time: configure build environment
make configure

# Build debug extension
make debug

# Run tests
make test
```

The compiled extension is at `build/debug/agent_data.duckdb_extension` (or `build/release/` for `make release`).

```bash
# Load directly from a local build
duckdb -unsigned -c "LOAD 'build/debug/agent_data.duckdb_extension'; FROM read_conversations();"
```

## Community Extension Release Checklist

When DuckDB publishes a new stable release, keep the community package aligned with
the latest stable target:

1. Check whether the repo is still aligned with DuckDB latest stable:

   ```bash
   python3 scripts/update_duckdb_release.py --check
   ```

2. If a new stable release exists, update all local release surfaces:

   ```bash
   python3 scripts/update_duckdb_release.py --apply
   ```

   This updates `duckdb-release.toml`, `Cargo.toml`, `Cargo.lock`,
   `Makefile`, `.github/workflows/MainDistributionPipeline.yml`, and
   example DuckDB Python constraints.

3. Run the full local validation entrypoint:

   ```bash
   scripts/validate_duckdb_release.sh
   ```

   This runs Rust/build/test checks and an exact-version DuckDB Python smoke
   test that loads `build/debug/agent_data.duckdb_extension`.

4. Update `duckdb/community-extensions` after the source commit is validated:

   ```bash
   scripts/prepare_community_extension_pr.py --open-pr
   ```

   Keep upstream `repo.ref` immutable. A commit SHA is preferred; an immutable
   tag is also acceptable when maintainers intentionally release by tag. Do not
   use `main` as the stable ref because community builds should be reproducible.

5. After the upstream community-extension workflow deploys from a trusted
   context, verify publication:

   ```bash
   uv run --with duckdb==$(python3 - <<'PY'
import tomllib
print(tomllib.load(open("duckdb-release.toml", "rb"))["duckdb"]["python_version"])
PY
) python scripts/verify_community_publication.py
   ```

   Pull-request deploys may build artifacts without publishing public binaries
   when upstream secrets are unavailable.

The scheduled `DuckDB Release Monitor` workflow checks for stable-release drift
and opens a PR when the updater and validation pass. The `DuckDB Next
Compatibility` workflow can be run on schedule or manually to test DuckDB
`main`/next without publishing binaries. For DuckDB feature-freeze branches,
use upstream `repo.ref_next` for pre-release validation, then update `repo.ref`
after the stable source commit is merged.

## License

MIT — see [LICENSE](LICENSE).
