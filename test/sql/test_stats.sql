-- Test: read_claude_stats basic functionality
-- This file tests the stats table function

-- Test 1: Get all daily stats
SELECT date, message_count, session_count, tool_call_count
FROM read_claude_stats('test/data')
ORDER BY date DESC;

-- Test 2: Total activity summary
SELECT 
    SUM(message_count) as total_messages,
    SUM(session_count) as total_sessions,
    SUM(tool_call_count) as total_tool_calls
FROM read_claude_stats('test/data');

-- Test 3: Average daily activity
SELECT 
    AVG(message_count) as avg_messages,
    AVG(session_count) as avg_sessions,
    AVG(tool_call_count) as avg_tool_calls
FROM read_claude_stats('test/data');

-- Test 4: Most active days
SELECT date, message_count
FROM read_claude_stats('test/data')
ORDER BY message_count DESC
LIMIT 3;

-- Test 5: Days with high tool usage
SELECT date, tool_call_count
FROM read_claude_stats('test/data')
WHERE tool_call_count > 100
ORDER BY tool_call_count DESC;

-- Test 6: Stats by date range
SELECT date, message_count, session_count
FROM read_claude_stats('test/data')
WHERE date >= '2026-02-01'
ORDER BY date;
