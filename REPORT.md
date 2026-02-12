# REPORT: Multi-Source Extension — Claude + Copilot Support

## Summary

Extended the `agent_data` DuckDB extension from Claude-only to support both Claude Code (`~/.claude`) and GitHub Copilot CLI (`~/.copilot`) data. All 5 table functions now auto-detect the data source and produce unified schemas with a `source` column. The architecture is extensible for future providers (Gemini, Codex, etc.).

**Total commits:** 8 (Tasks 1–8)
**Test assertions:** 104 SQL + 11 Python smoke test checks (115 total)
**Lines changed:** ~1,200 added, ~400 removed across 25 files

---

## Task 1: Copilot Documentation

**Commit:** `c43df04` — *docs: add Copilot CLI file structure and schema documentation*

Created two documentation files parallel to existing Claude docs:

- **`docs/COPILOT_FILE_STRUCTURE.md`** — Complete directory layout of `~/.copilot/`, including `session-state/` hierarchy, `workspace.yaml`, `events.jsonl`, `plan.md`, `checkpoints/`, `command-history-state.json`, `config.json`, and `logs/`.

- **`docs/COPILOT_FILE_SCHEMAS.md`** — Detailed JSON schemas for all 16 Copilot event types with example payloads, workspace.yaml YAML schema, command-history-state.json format, and config.json structure.

**Key finding:** Copilot uses an event-sourced model (16 distinct event types with a common envelope `{type, id, timestamp, parentId, data}`) vs Claude's message-per-line JSONL format. Session metadata lives in `workspace.yaml` rather than embedded in each message.

---

## Task 2: Provider Detection + Types Split

**Commit:** `f434cab` — *refactor: add provider detection, split types module, define Copilot event types*

Infrastructure changes with zero behavioral impact:

- **`src/detect.rs`** (43 LOC) — `Provider` enum (`Claude`, `Copilot`, `Unknown`), `detect_provider()` heuristic (checks for `projects/` → Claude, `session-state/` → Copilot), `parse_source()` for explicit overrides, `resolve_provider()` combining both.

- **`src/types/` module split** — Moved `types.rs` → `types/claude.rs`, created `types/copilot.rs` with 15 serde structs covering all Copilot event types: `CopilotEvent` envelope, `SessionStartData`, `SessionContext`, `AssistantMessageData`, `ToolRequest`, `ToolExecutionStartData`, `ToolExecutionCompleteData`, `ToolResult`, `ModelChangeData`, `TruncationData`, `UserMessageData`, `ReasoningData`, `SessionErrorData`, `CopilotCommandHistory`, `WorkspaceYaml`.

- **`src/utils.rs`** — Added 6 new functions: `resolve_data_path()`, `discover_copilot_event_files()`, `discover_copilot_plan_files()`, `discover_copilot_checkpoint_files()`, `copilot_history_file_path()`, `read_workspace_yaml()`.

- **`src/vtab.rs`** — Added `source` named parameter alongside `path`. Updated `TableFunc` trait: `load_rows(path, source)`.

- **Dependencies:** Added `serde_yaml = "0.9"` for workspace.yaml parsing.

All 54 existing tests continued to pass (load_rows functions accepted but ignored the new `source` parameter).

---

## Task 3: Copilot Test Data

**Commit:** `db341a8` — *test: add synthetic Copilot CLI test data*

Created `test/data_copilot/` matching the real `~/.copilot/` structure:

| Component | Details |
|-----------|---------|
| Sessions | 4 (3 directory-based + 1 root-level JSONL) |
| Total events | 53 across all sessions |
| Event types | All 16 types represented |
| Session 1 (aaaa) | 30 events, checkpoints with 4 todo items |
| Session 2 (bbbb) | 10 events, plan.md with 3 checklist items |
| Session 3 (cccc) | 8 events, same project as session 1 |
| Session 4 (dddd) | 5 events, root-level JSONL (no workspace.yaml) |
| Command history | 5 command strings |
| Config | Model + user preferences |

Data uses the proper Copilot event envelope format (`data: {}` wrapper) validated against real `copilot_raw/` samples.

---

## Task 4: Unified Conversations

**Commit:** `0587991` — *feat: unified conversations table with Claude + Copilot support*

The largest task — complete rewrite of `conversations.rs` (252 → 310 LOC):

**Schema changes:**
- Added `source` column (first column, `'claude'` or `'copilot'`)
- Added `repository` column (last column, Copilot GitHub repo context)
- Total: 27 columns (was 25)

**Copilot event loading:**
- Parses `events.jsonl` line by line as `CopilotEvent`
- Reads `workspace.yaml` for session metadata (id, cwd, branch, repository)
- Extracts session context from `session.start` events
- Maps all 16 event types to normalized `message_type` values
- Tracks model changes via `session.model_change` events
- Backfills session metadata (session_id, cwd, branch, repo, version) to all events

**Message type mapping:**

| Copilot Event | → message_type | message_role |
|--------------|----------------|--------------|
| `user.message` | `user` | `user` |
| `assistant.message` | `assistant` | `assistant` |
| `assistant.reasoning` | `reasoning` | `assistant` |
| `tool.execution_start` | `tool_start` | `tool` |
| `tool.execution_complete` | `tool_result` | `tool` |
| `session.start` | `session_start` | NULL |
| `session.truncation` | `truncation` | NULL |
| ... (16 total) | | |

**Test coverage:** 18 new assertions in `test_copilot_conversations.sql` + 1 Claude source verification.

**Real data validation:** 91,096 Copilot events loaded from `copilot_raw/` — all 16 event types, correct session metadata coverage (91K session_ids, 49K repositories, 52K branches, 91K versions).

---

## Task 5: Unified Plans + History + Todos + Stats

**Commit:** `98579c8` — *feat: unified plans, history, todos, stats with Copilot support*

Updated all remaining modules:

### Plans (`plans.rs`)
- Added `source` + `session_id` columns (7 total, was 5)
- Copilot: loads `session-state/*/plan.md`, uses workspace summary as plan_name
- Claude: session_id is NULL (plans are global)
- 7 new test assertions

### History (`history.rs`)
- Added `source` column (7 total, was 6)
- Copilot: loads `command-history-state.json` array
- Copilot entries have NULL timestamps/project/session_id (simpler format)
- 6 new test assertions

### Todos (`todos.rs`)
- Added `source` column, made `agent_id` optional (8 total, was 7)
- Copilot: extracts markdown checklists from `checkpoints/*.md`
- Parses `- [x] completed` and `- [ ] pending` patterns
- agent_id is NULL for Copilot
- 9 new test assertions

### Stats (`stats.rs`)
- Added `source` column (5 total, was 4)
- Returns empty for Copilot (no equivalent data)

**Real data validation:**

| Table | Claude (claude_raw/) | Copilot (copilot_raw/) |
|-------|---------------------|----------------------|
| Plans | 23 | 23 |
| History | 663 | 50 |
| Todos | 152 | 376 |
| Stats | 18 | 0 |

---

## Task 6: Cross-Source Tests + Smoke Test

**Commit:** `ef6c91f` — *test: add cross-source tests and update smoke test for Copilot*

- **`test/sql/test_cross_source.sql`** — 10 assertions testing:
  - UNION ALL across sources (conversations=233, plans=5, history=25, todos=22)
  - Source filtering in UNION results
  - Session ID isolation (no cross-source collision)
  - Provider-specific message types present in union
  - Claude-specific columns NULL for Copilot (slug)
  - Repository column isolation (Copilot only)
  - Group by source across combined data

- **`scripts/smoke_test.sh`** — Added Copilot data validation:
  - Verifies conversations=53, plans=1, todos=4, history=5, stats=0
  - Checks source + repository DataFrame columns present

**Total test count after this task:** 104 SQL + 11 smoke = 115 assertions.

---

## Task 7: Marimo Notebook Update

**Commit:** `ae79a6d` — *feat: update marimo notebook for multi-source exploration*

Updated `examples/explore.py` for multi-source support:

- Loads data from both `DATA_PATH` and `COPILOT_DATA_PATH` via UNION ALL
- Overview table shows row counts broken down by source
- Conversations grouped by `source` + `message_type`
- Session explorer dropdown shows `[source]` prefix
- Session messages include `source` column
- Todos grouped by `source` + `status`
- Plans table shows `source` + `session_id`
- History handles missing timestamps (Copilot has none)
- Cross-source analysis with source-aware joins
- Environment variables: `AGENT_DATA_PATH`, `COPILOT_DATA_PATH`, `AGENT_DATA_EXT`

---

## Task 8: Documentation Update

**Commit:** `a7a9e2d` — *docs: update README and instructions for multi-source support*

### README.md
- Updated title and scope (Claude + Copilot, extensible)
- New Quick Start with both sources + UNION example
- Complete API reference with all 5 tables showing unified schemas
- Message type mapping table (Claude ↔ Copilot)
- Provider detection documentation
- Updated join keys (source-aware)
- Updated test counts (104+)
- Architecture section with new file structure

### .copilot-instructions.md
- Updated project structure (detect.rs, types/ split, test/data_copilot/)
- Provider detection heuristic documentation
- New provider addition guide (5-step process)
- Updated API examples with source parameter
- Updated test counts and verification checklist

---

## Architecture Summary

### Provider Detection Flow
```
path → detect_provider(path)
        ├── projects/ dir exists → Claude
        ├── session-state/ dir exists → Copilot
        └── neither → Unknown

source param → parse_source(source)
                ├── "claude" → Claude
                └── "copilot" → Copilot

resolve_provider(path, source) = source override || auto-detect
```

### Module Loading Pattern
```rust
fn load_rows(path, source) {
    let base_path = resolve_data_path(path);
    match resolve_provider(&base_path, source) {
        Claude  → load_claude_rows(&base_path),
        Copilot → load_copilot_rows(&base_path),
        Unknown → Vec::new(),
    }
}
```

### File Structure
```
src/
├── lib.rs              # Entry (5 function registrations)
├── vtab.rs             # Generic VTab (path + source params)
├── detect.rs           # Provider enum + detection
├── types/
│   ├── mod.rs          # Re-exports
│   ├── claude.rs       # 10 Claude serde types
│   └── copilot.rs      # 15 Copilot serde types
├── utils.rs            # 12 discovery functions (6 Claude + 6 Copilot)
├── conversations.rs    # Unified (310 LOC)
├── plans.rs            # Unified (83 LOC)
├── todos.rs            # Unified (118 LOC)
├── history.rs          # Unified (100 LOC)
└── stats.rs            # Unified (55 LOC)
```

### Test Structure
```
test/
├── data/               # Claude synthetic (180 conversations)
├── data_copilot/       # Copilot synthetic (53 events)
└── sql/
    ├── test_conversations.sql      # 16 assertions
    ├── test_copilot_conversations.sql  # 18 assertions
    ├── test_plans.sql              # 6 assertions
    ├── test_copilot_plans.sql      # 7 assertions
    ├── test_todos.sql              # 8 assertions
    ├── test_copilot_todos.sql      # 9 assertions
    ├── test_history.sql            # 7 assertions
    ├── test_copilot_history.sql    # 6 assertions
    ├── test_stats.sql              # 5 assertions
    ├── test_joins.sql              # 10 assertions
    ├── test_cross_source.sql       # 10 assertions
    └── test_benchmark.sql          # 2 assertions
```

---

## Extensibility

To add a new provider (e.g., Gemini):

1. Add `Gemini` to `Provider` enum in `detect.rs`
2. Add detection heuristic (e.g., check for `gemini-sessions/` directory)
3. Create `src/types/gemini.rs` with serde types
4. Add discovery functions in `utils.rs`
5. Add `Provider::Gemini =>` branches in each module's `load_rows()`
6. Create `test/data_gemini/` synthetic test data
7. Add `test/sql/test_copilot_*.sql` test files

The unified schema approach means new providers just need to map their data to existing columns (with NULL for unsupported fields) and optionally add provider-specific columns.
