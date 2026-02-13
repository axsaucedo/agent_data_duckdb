# agent_data DuckDB Extension - Development Instructions

## Critical Caveats

### 1. JSONL File Handling - DANGER ZONE
**⚠️ NEVER print, cat, or view full JSONL files from claude_raw/, copilot_raw/ or test/data/**

The JSONL conversation files can be **massive** (hundreds of MB). Incorrect commands will:
- Pollute the entire context window
- Cause memory issues
- Result in incomplete/corrupted output

**Safe Commands:**
```bash
# View first N bytes only
head -c 500 file.jsonl

# Count lines without reading content
wc -l file.jsonl

# Get first N complete JSON lines
head -n 3 file.jsonl | jq -c '.'

# Sample specific fields only
head -n 10 file.jsonl | jq -c '{type, timestamp}'

# Get file size
ls -lh file.jsonl
```

**NEVER DO:**
```bash
cat file.jsonl           # DANGEROUS
less file.jsonl          # DANGEROUS (without limits)
jq '.' file.jsonl        # DANGEROUS (reads entire file)
```

### 2. Build and Test
```bash
make configure   # First time setup
make debug       # Build debug extension
make test        # Build + run all tests
```

### 3. Testing Strategy
- Always run tests with limited data first
- Use `test/data/` (Claude) and `test/data_copilot/` (Copilot) synthetic data
- Never use `claude_raw/` or `copilot_raw/` for automated tests
- Run `make test` after every change
- Tests are assertion-driven (PASS/FAIL output)

## Project Structure

```
agentic-copilot/
├── .copilot-instructions.md  # THIS FILE
├── Cargo.toml                # Rust crate (agent_data)
├── Makefile                  # Build system
├── src/                      # Rust extension source
│   ├── lib.rs               # Entry point (registers 5 functions)
│   ├── vtab.rs              # Generic VTab framework (TableFunc trait)
│   ├── detect.rs            # Provider auto-detection (Claude/Copilot)
│   ├── types/
│   │   ├── mod.rs           # Re-exports
│   │   ├── claude.rs        # Claude JSON/JSONL serde types
│   │   └── copilot.rs       # Copilot event serde types
│   ├── utils.rs             # Path resolution, file discovery (both providers)
│   ├── conversations.rs     # Unified read_conversations()
│   ├── plans.rs             # Unified read_plans()
│   ├── todos.rs             # Unified read_todos()
│   ├── history.rs           # Unified read_history()
│   └── stats.rs             # read_stats() (Claude only)
├── test/
│   ├── data/                # Synthetic Claude data (~/.claude mock)
│   ├── data_copilot/        # Synthetic Copilot data (~/.copilot mock)
│   └── sql/                 # SQL test files (104+ assertions)
├── scripts/
│   ├── test.sh              # SQL test runner
│   └── smoke_test.sh        # Python/DuckDB smoke test
├── examples/
│   └── explore.py           # Marimo notebook (multi-source)
├── docs/                    # Documentation
│   ├── CLAUDE_FILE_STRUCTURE.md
│   ├── CLAUDE_FILE_SCHEMAS.md
│   ├── COPILOT_FILE_STRUCTURE.md
│   ├── COPILOT_FILE_SCHEMAS.md
│   └── DUCKDB_EXTENSION_PATTERNS.md
├── claude_raw/              # Real Claude data - READ ONLY, HANDLE WITH CARE
└── copilot_raw/             # Real Copilot data - READ ONLY, HANDLE WITH CARE
```

## Architecture

The extension uses a **generic VTab framework** with provider auto-detection:

- `vtab.rs`: `TableFunc` trait with `columns()`, `load_rows(path, source)`, `write_row()`
- `detect.rs`: `Provider` enum (`Claude`, `Copilot`, `Unknown`) + `detect_provider()` heuristic
- Each module dispatches to provider-specific loaders based on auto-detection or explicit `source` parameter
- `GenericVTab<T>`: handles all DuckDB VTab lifecycle generically

**Provider detection heuristic:**
- `projects/` directory → Claude
- `session-state/` directory → Copilot
- Neither → Unknown (returns empty, or use `source` param)

To add a new provider:
1. Add variant to `Provider` enum in `detect.rs`
2. Add detection heuristic in `detect_provider()`
3. Add serde types in `types/<provider>.rs`
4. Add discovery functions in `utils.rs`
5. Add loader branch in each table module's `load_rows()`

## Extension API

All functions accept `path` and `source` parameters:

```sql
LOAD 'build/debug/agent_data.duckdb_extension';

-- Auto-detect provider from directory structure
SELECT * FROM read_conversations(path='~/.claude');
SELECT * FROM read_conversations(path='~/.copilot');

-- Explicit source override
SELECT * FROM read_conversations(path='test/data_copilot', source='copilot');

-- UNION both sources
SELECT * FROM read_conversations(path='~/.claude')
UNION ALL
SELECT * FROM read_conversations(path='~/.copilot');
```

Every table has `source` as the first column (`'claude'` or `'copilot'`).

## Key Join Keys

- `session_id`: links conversations ↔ history ↔ todos (within same source)
- `project_path` / `project`: links conversations ↔ history (Claude only)
- `slug` / `plan_name`: links conversations ↔ plans (Claude only)
- `source`: always filter or join by source when mixing data

## Verification Checklist

Before committing:
- [ ] `make test` passes (104+ SQL tests + Python smoke test)
- [ ] No large files accidentally committed
- [ ] Build artifacts excluded from git
- [ ] Documentation updated if API changes
- [ ] New provider data has corresponding test data in `test/data_<provider>/`
