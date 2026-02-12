#!/bin/bash
# Smoke test: verify extension loads correctly via Python/DuckDB
# Validates that the marimo notebook code path works end-to-end
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
EXT_PATH="$PROJECT_DIR/build/debug/agent_data.duckdb_extension"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

if [ ! -f "$EXT_PATH" ]; then
    echo -e "${RED}Extension not found at $EXT_PATH${NC}"
    echo "Run 'make debug' first."
    exit 1
fi

echo "Running Python/DuckDB smoke test..."

python3 -c "
import duckdb, sys

con = duckdb.connect(config={'allow_unsigned_extensions': 'true'})
con.execute(\"LOAD '${EXT_PATH}'\")

expected = {
    'conversations': 180,
    'plans': 4,
    'todos': 18,
    'history': 20,
    'stats': 7,
}

failed = False
for table, expected_count in expected.items():
    df = con.execute(f\"SELECT * FROM read_{table}(path='test/data')\").df()
    actual = len(df)
    if actual != expected_count:
        print(f'FAIL: {table} expected {expected_count} rows, got {actual}')
        failed = True
    else:
        print(f'PASS: {table} = {actual} rows')

# Verify Copilot data loading
copilot_expected = {
    'conversations': 53,
    'plans': 1,
    'todos': 4,
    'history': 5,
    'stats': 0,
}

for table, expected_count in copilot_expected.items():
    df = con.execute(f\"SELECT * FROM read_{table}(path='test/data_copilot')\").df()
    actual = len(df)
    if actual != expected_count:
        print(f'FAIL: copilot {table} expected {expected_count} rows, got {actual}')
        failed = True
    else:
        print(f'PASS: copilot {table} = {actual} rows')

# Verify DataFrame columns are accessible (ensures pandas compatibility)
conv = con.execute(\"SELECT * FROM read_conversations(path='test/data') LIMIT 1\").df()
required_cols = ['source', 'session_id', 'project_path', 'message_type', 'uuid', 'timestamp', 'repository']
for col in required_cols:
    if col not in conv.columns:
        print(f'FAIL: missing column {col}')
        failed = True

if not failed:
    print('PASS: all DataFrame columns present')

sys.exit(1 if failed else 0)
"

STATUS=$?
if [ $STATUS -eq 0 ]; then
    echo -e "${GREEN}Python smoke test passed!${NC}"
else
    echo -e "${RED}Python smoke test failed!${NC}"
    exit 1
fi
