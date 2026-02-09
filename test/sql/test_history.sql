-- Test: read_claude_history basic functionality
-- This file tests the history table function

-- Test 1: List all history entries
SELECT timestamp, project, display
FROM read_claude_history('test/data/')
ORDER BY timestamp DESC
LIMIT 20;

-- Test 2: Count total history entries
SELECT COUNT(*) as total_entries
FROM read_claude_history('test/data/');

-- Test 3: History entries per project
SELECT project, COUNT(*) as entry_count
FROM read_claude_history('test/data/')
GROUP BY project
ORDER BY entry_count DESC;

-- Test 4: Search history by display content
SELECT timestamp, project, display
FROM read_claude_history('test/data/')
WHERE display LIKE '%init%' OR display LIKE '%test%';

-- Test 5: History entries with session IDs
SELECT timestamp, project, session_id, display
FROM read_claude_history('test/data/')
WHERE session_id IS NOT NULL
LIMIT 10;

-- Test 6: Most recent history entries
SELECT timestamp, project, display
FROM read_claude_history('test/data/')
ORDER BY timestamp DESC
LIMIT 5;

-- Test 7: History entries by date range
SELECT timestamp, project, display
FROM read_claude_history('test/data/')
WHERE timestamp >= '2025-01-01'
ORDER BY timestamp;
