-- Test: Cross-table joins and corner cases
-- This file tests advanced queries and edge cases

-- ============================================
-- Cross-table Join Tests
-- ============================================

-- Test 1: Join conversations with history
SELECT 
    c.session_id,
    c.message_type,
    h.display as history_entry
FROM read_claude_conversations('test/data/') c
LEFT JOIN read_claude_history('test/data/') h 
    ON c.session_id = h.session_id
WHERE h.session_id IS NOT NULL
LIMIT 10;

-- Test 2: Join todos with conversations (by session)
SELECT 
    t.session_id,
    t.content as todo_content,
    t.status,
    COUNT(c.message_uuid) as message_count
FROM read_claude_todos('test/data/') t
LEFT JOIN read_claude_conversations('test/data/') c 
    ON t.session_id = c.session_id
GROUP BY t.session_id, t.content, t.status
LIMIT 10;

-- Test 3: Correlate plans with conversation slugs
SELECT 
    p.plan_name,
    p.slug,
    c.session_id,
    c.timestamp
FROM read_claude_plans('test/data/') p
LEFT JOIN read_claude_conversations('test/data/') c 
    ON p.slug = c.slug
WHERE c.session_id IS NOT NULL
LIMIT 10;

-- ============================================
-- Corner Case Tests
-- ============================================

-- Test 4: Handle NULL values
SELECT 
    message_uuid,
    COALESCE(parent_uuid, 'NO_PARENT') as parent,
    COALESCE(model, 'UNKNOWN') as model
FROM read_claude_conversations('test/data/')
LIMIT 10;

-- Test 5: Empty string handling
SELECT plan_name, LENGTH(content)
FROM read_claude_plans('test/data/')
WHERE content != '';

-- Test 6: JSON field extraction with missing keys
SELECT 
    session_id,
    json_extract(token_usage, '$.input_tokens') as input_tokens,
    json_extract(token_usage, '$.nonexistent_key') as missing_key
FROM read_claude_conversations('test/data/')
WHERE message_type = 'assistant'
LIMIT 5;

-- Test 7: Timestamp ordering consistency
SELECT timestamp, message_type
FROM read_claude_conversations('test/data/')
ORDER BY timestamp ASC
LIMIT 5;

-- Test 8: Large content handling
SELECT 
    message_uuid,
    LENGTH(content) as content_length,
    CASE 
        WHEN LENGTH(content) > 1000 THEN 'LARGE'
        WHEN LENGTH(content) > 100 THEN 'MEDIUM'
        ELSE 'SMALL'
    END as size_category
FROM read_claude_conversations('test/data/')
WHERE content IS NOT NULL;

-- Test 9: UUID format validation
SELECT message_uuid
FROM read_claude_conversations('test/data/')
WHERE message_uuid SIMILAR TO '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
LIMIT 5;

-- Test 10: Project path decoding
SELECT DISTINCT project_path
FROM read_claude_conversations('test/data/')
WHERE project_path LIKE '%-Users-%';

-- ============================================
-- Aggregation Tests
-- ============================================

-- Test 11: Complex aggregation
SELECT 
    DATE_TRUNC('day', timestamp) as day,
    COUNT(*) as messages,
    COUNT(DISTINCT session_id) as sessions
FROM read_claude_conversations('test/data/')
WHERE timestamp IS NOT NULL
GROUP BY DATE_TRUNC('day', timestamp)
ORDER BY day;

-- Test 12: Tool usage frequency
SELECT 
    json_extract(tool_use.value, '$.name') as tool_name,
    COUNT(*) as usage_count
FROM read_claude_conversations('test/data/'),
    LATERAL unnest(json_extract(tool_uses, '$')::JSON[]) as tool_use(value)
WHERE tool_uses IS NOT NULL
GROUP BY tool_name
ORDER BY usage_count DESC;

-- ============================================
-- Error Condition Tests (should handle gracefully)
-- ============================================

-- Test 13: Non-existent path (should return error or empty)
-- Note: This tests error handling in the extension
-- SELECT * FROM read_claude_conversations('/nonexistent/path/');

-- Test 14: Empty directory handling
-- Extension should handle directories with no matching files
