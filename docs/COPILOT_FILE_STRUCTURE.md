# Copilot CLI File Structure

## Overview

The GitHub Copilot CLI stores session data in `~/.copilot/` with a fundamentally different structure from Claude Code. While Claude organizes data by project path, Copilot organizes data by session UUID.

## Root Directory (`~/.copilot/`)

```
~/.copilot/
├── config.json                     # Global configuration and authentication
├── command-history-state.json      # Persistent command history
├── ide/                            # IDE-specific data (typically empty for CLI)
├── logs/                           # Process and session logs
│   ├── process-<timestamp>-<pid>.log
│   └── session-<uuid>.log
└── session-state/                  # Per-session data (primary data store)
    ├── <uuid>/                     # Session directory
    │   ├── events.jsonl            # Session event log (conversations)
    │   ├── workspace.yaml          # Session metadata
    │   ├── plan.md                 # Optional: planning notes
    │   ├── checkpoints/            # Checkpoint snapshots
    │   │   ├── index.md            # Checkpoint index
    │   │   └── 001-<slug>.md       # Individual checkpoint docs
    │   ├── files/                  # Uploaded/pasted file attachments
    │   └── rewind-snapshots/       # Point-in-time snapshots
    │       ├── index.json          # Snapshot metadata
    │       └── backups/            # Backup archives
    └── <uuid>.jsonl                # Some sessions store events at root level
```

## Key Files

### `config.json` — Global Configuration
User preferences and authentication state. Not session-specific.

### `command-history-state.json` — Command History
A JSON object with a `commandHistory` array of command strings. Unlike Claude's `history.jsonl`, this has no timestamps, project paths, or session IDs — just the raw command text.

### `session-state/<uuid>/events.jsonl` — Session Events
The primary conversation data. Each line is a JSON event with a common envelope:
```json
{"type": "...", "id": "uuid", "timestamp": "ISO-8601", "parentId": "uuid|null", "data": {...}}
```
16 distinct event types (see COPILOT_FILE_SCHEMAS.md for details).

### `session-state/<uuid>/workspace.yaml` — Session Metadata
YAML file with session context:
```yaml
id: <uuid>
cwd: /path/to/project
git_root: /path/to/repo
repository: owner/repo
branch: main
summary: Session description
summary_count: 1
created_at: 2026-02-11T19:33:46.140Z
updated_at: 2026-02-11T19:56:41.841Z
```

### `session-state/<uuid>/plan.md` — Session Plans
Optional markdown planning documents created during planning mode. Not all sessions have plans.

### `session-state/<uuid>/checkpoints/` — Checkpoints
Checkpoint snapshots with an `index.md` linking to individual checkpoint `.md` files. Checkpoints may contain markdown checklists (`- [x]`/`- [ ]`) that function as todo items.

## Naming Patterns

| Entity | Pattern | Example |
|--------|---------|---------|
| Session directory | UUID | `37f4ab8c-bc13-40e9-83a7-72ce36644c1c` |
| Events file | `events.jsonl` | Fixed name within session dir |
| Root-level events | `<uuid>.jsonl` | `1440d44f-1dee-4c31-bb69-e8bd7fd918b2.jsonl` |
| Process logs | `process-<timestamp>-<pid>.log` | `process-1769877557429-80086.log` |
| Session logs | `session-<uuid>.log` | `session-ea7fc8a2-...log` |
| Checkpoints | `<NNN>-<slug>.md` | `001-two-phase-agentic-loop-impleme.md` |

## Entity Relationships

```
Session (workspace.yaml)
  ├── Events (events.jsonl) — conversation flow
  ├── Plan (plan.md) — optional planning document
  ├── Checkpoints (checkpoints/) — progress snapshots with checklists
  └── Snapshots (rewind-snapshots/) — point-in-time recovery
```

## Comparison with Claude Code

| Aspect | Claude | Copilot |
|--------|--------|---------|
| Organization | By project path | By session UUID |
| Conversations | One file per session, per project | One events.jsonl per session |
| Session metadata | Embedded in message fields | Separate workspace.yaml |
| Sub-agents | Separate `agent-*.jsonl` files | No separate agent files |
| Plans | Global `plans/*.md` directory | Per-session `plan.md` |
| Todos | Structured JSON in `todos/` | Markdown checklists in checkpoints |
| History | Structured JSONL with metadata | Simple string array |
| Stats | Daily activity aggregates | No equivalent |
