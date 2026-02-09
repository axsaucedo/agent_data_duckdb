# Claude Code DuckDB Extension - Implementation Plan

## Overview

This project creates a DuckDB extension that can parse and query Claude Code data directories (typically `~/.claude`). The extension exposes Claude Code metadata, conversations, plans, and todos as queryable tables.

## Architecture

```
agentic-copilot/
├── .copilot-instructions.md     # Development guidelines and caveats
├── docs/
│   ├── CLAUDE_FILE_STRUCTURE.md  # File/folder hierarchy documentation
│   └── CLAUDE_FILE_SCHEMAS.md    # JSON/data schemas documentation
├── scripts/
│   ├── analyze_structure.py      # Analyze copilot_raw structure
│   ├── generate_test_data.py     # Generate synthetic test data
│   └── verify.sh                 # Build and test verification
├── test/
│   ├── data/                     # Synthetic test data (mock ~/.claude)
│   └── sql/                      # SQL test queries
└── claude_code_ext/              # DuckDB extension (renamed from extension-template-c)
    ├── src/
    │   ├── claude_code_ext.c     # Extension entry point
    │   ├── json_parser.c         # JSON/JSONL parsing utilities
    │   ├── conversations.c       # Conversation table function
    │   ├── plans.c               # Plans table function
    │   └── todos.c               # Todos table function
    └── CMakeLists.txt
```

## Data Model

### Key Claude Code Data Types

1. **Conversations** (`projects/<project>/<session-id>.jsonl`)
   - Main interaction logs between user and Claude
   - Line-delimited JSON with message objects

2. **Plans** (`plans/<plan-name>.md`)
   - Markdown files with implementation plans
   - Created via plan tool during conversations

3. **Todos** (`todos/<session-agent>.json`)
   - JSON arrays with todo items
   - Status: pending, in_progress, completed

4. **History** (`history.jsonl`)
   - Global command/prompt history across projects
   - Includes timestamps and project paths

5. **File History** (`file-history/<session>/<hash>@<version>`)
   - Backups of modified files
   - Versioned by content hash

### Relationships

- Conversations reference plans via plan tool calls
- Conversations reference todos via update_todo tool calls
- Conversations spawn sub-agents (agent-*.jsonl files)
- History entries reference projects

## Implementation Phases

### Phase 1: Setup & Analysis (Tasks 1-3)
- Create development guidelines
- Analyze copilot_raw structure programmatically
- Document file structure and schemas

### Phase 2: Test Infrastructure (Tasks 4-5)
- Generate synthetic test data
- Create SQL test cases

### Phase 3: Extension Development (Tasks 6-8)
- Research DuckDB extension patterns
- Implement C extension
- Build and test

### Phase 4: Finalization (Task 9)
- Complete documentation
- Final verification
- Commit all changes

## DuckDB Extension Functions

```sql
-- Read conversations from a Claude data directory
SELECT * FROM read_claude_conversations('/path/to/.claude');

-- Read plans
SELECT * FROM read_claude_plans('/path/to/.claude');

-- Read todos
SELECT * FROM read_claude_todos('/path/to/.claude');

-- Read history
SELECT * FROM read_claude_history('/path/to/.claude');

-- Join conversations with their plans
SELECT c.session_id, c.project, p.plan_name, p.content
FROM read_claude_conversations('/path/to/.claude') c
JOIN read_claude_plans('/path/to/.claude') p 
  ON c.plan_reference = p.plan_name;
```

## Critical Development Considerations

1. **JSONL files can be MASSIVE** - Never cat/print full files
2. **Use head/tail/jq with limits** - Always limit output
3. **Build in tmp/** - Keep build artifacts local
4. **Test incrementally** - Verify each component
5. **Use C API template** - More stable than C++ API
