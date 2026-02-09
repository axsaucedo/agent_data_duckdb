#!/bin/bash
# Verification script for Claude Code DuckDB Extension
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
EXT_DIR="$PROJECT_DIR/claude_code_ext"
TEST_DATA_DIR="$PROJECT_DIR/test/data"
TEST_SQL_DIR="$PROJECT_DIR/test/sql"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "========================================"
echo "Claude Code DuckDB Extension Verifier"
echo "========================================"
echo ""

# Check prerequisites
echo "Checking prerequisites..."
if ! command -v duckdb &> /dev/null; then
    echo -e "${RED}ERROR: duckdb is not installed${NC}"
    exit 1
fi
DUCKDB_VERSION=$(duckdb --version | head -1)
echo -e "${GREEN}✓ DuckDB found: $DUCKDB_VERSION${NC}"

# Build extension
echo ""
echo "Building extension..."
cd "$EXT_DIR"

# Clone extension-ci-tools if not present
if [ ! -d "extension-ci-tools" ]; then
    echo "  Cloning extension-ci-tools..."
    git clone --depth 1 -b v1.4.4 https://github.com/duckdb/extension-ci-tools extension-ci-tools 2>/dev/null
fi

make clean > /dev/null 2>&1 || true
rm -rf configure 2>/dev/null || true

# Create version file
mkdir -p configure
echo "0.1.0" > configure/extension_version.txt

make 2>&1 | tee /tmp/build_output.txt | tail -5
if [ -f "$EXT_DIR/build/release/claude_code.duckdb_extension" ]; then
    echo -e "${GREEN}✓ Extension built successfully${NC}"
else
    echo -e "${RED}ERROR: Extension build failed${NC}"
    cat /tmp/build_output.txt | tail -30
    exit 1
fi

EXTENSION_PATH="$EXT_DIR/build/release/claude_code.duckdb_extension"

# Verify extension loads
echo ""
echo "Testing extension loading..."
if duckdb -unsigned -c "LOAD '$EXTENSION_PATH';" 2>&1 | grep -q "Error"; then
    echo -e "${RED}ERROR: Extension failed to load${NC}"
    duckdb -unsigned -c "LOAD '$EXTENSION_PATH';" 2>&1
    exit 1
fi
echo -e "${GREEN}✓ Extension loads successfully${NC}"

# Test each function
echo ""
echo "Testing table functions..."

test_function() {
    local func_name="$1"
    local expected_min="$2"
    
    result=$(duckdb -unsigned -c "LOAD '$EXTENSION_PATH'; SELECT COUNT(*) FROM $func_name('$TEST_DATA_DIR');" 2>&1)
    if echo "$result" | grep -q "Error"; then
        echo -e "${RED}✗ $func_name: FAILED${NC}"
        echo "  $result"
        return 1
    fi
    
    count=$(echo "$result" | grep -E "^\│" | head -1 | sed 's/[^0-9]//g')
    if [ -z "$count" ]; then
        count=$(echo "$result" | grep -E "^[0-9]+" | head -1)
    fi
    
    echo -e "${GREEN}✓ $func_name: returned $count rows${NC}"
    return 0
}

FAILED=0
test_function "read_claude_conversations" 1 || FAILED=1
test_function "read_claude_plans" 1 || FAILED=1
test_function "read_claude_todos" 1 || FAILED=1
test_function "read_claude_history" 1 || FAILED=1
test_function "read_claude_stats" 1 || FAILED=1

# Run SQL test files
echo ""
echo "Running SQL test files..."
for sql_file in "$TEST_SQL_DIR"/*.sql; do
    if [ -f "$sql_file" ]; then
        filename=$(basename "$sql_file")
        echo -n "  Testing $filename... "
        
        # Create modified SQL with extension load and path substitution
        modified_sql=$(cat "$sql_file" | sed "s|'test/data'|'$TEST_DATA_DIR'|g" | sed "s|'/path/to/.claude'|'$TEST_DATA_DIR'|g")
        
        result=$(echo "LOAD '$EXTENSION_PATH'; $modified_sql" | duckdb -unsigned 2>&1)
        # Check for actual SQL errors (Binder Error, Parser Error, etc.) not just the word "error"
        if echo "$result" | grep -qE "(Binder Error|Parser Error|Catalog Error|Invalid Input Error|IO Error|Internal Error)"; then
            echo -e "${RED}FAILED${NC}"
            echo "$result" | grep -E "(Error:|error:)" | head -5
            FAILED=1
        else
            echo -e "${GREEN}OK${NC}"
        fi
    fi
done

# Summary
echo ""
echo "========================================"
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed!${NC}"
    exit 1
fi
