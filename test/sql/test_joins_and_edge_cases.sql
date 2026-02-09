-- Test: Cross-table joins and corner cases
-- This file tests advanced queries and edge cases

-- ============================================
-- Cross-table Join Tests
-- ============================================

-- Test 1: Join conversations with history
SELECT 
    c.session_id,
    c.type,
    h.display as history_entry
FROM read_claude_conversations('test/data') c
LEFT JOIN read_claude_history('test/data') h 
    ON c.session_id = h.session_id
WHERE h.session_id IS NOT NULL
LIMIT 10;

-- Test 2: Join todos with conversations (by session)
SELECT 
    t.session_id,
    t.content as todo_content,
    t.status,
    COUNT(c.uuid) as message_count
FROM read_claude_todos('test/data') t
LEFT JOIN read_claude_conversations('test/data') c 
    ON t.session_id = c.session_id
GROUP BY t.session_id, t.content, t.status
LIMIT 10;

-- Test 3: Correlate plans with conversation slugs
SELECT 
    p.plan_name,
    c.session_id,
    c.timestamp
FROM read_claude_plans('test/data') p
LEFT JOIN read_claude_conversations('test/data') c 
    ON p.plan_name = c.slug
WHERE c.session_id IS NOT NULL
LIMIT 10;

-- ============================================
-- Corner Case Tests
-- ============================================

-- Test 4: Handle NULL values
SELECT 
    uuid,
    COALESCE(parent_uuid, 'NO_PARENT') as parent,
    COALESCE(version, 'UNKNOWN') as version_val
FROM read_claude_conversations('test/data')
LIMIT 10;

-- Test 5: Empty string handling
SELECT plan_name, LENGTH(content)
FROM read_claude_plans('test/data')
WHERE content != '';

-- Test 6: Tool name extraction
SELECT 
    session_id,
    tool_name,
    tool_use_id
FROM read_claude_conversations('test/data')
WHERE message_role = 'assistant' AND tool_name IS NOT NULL
LIMIT 5;

-- Test 7: Timestamp ordering consistency
SELECT timestamp, type
FROM read_claude_conversations('test/data')
ORDER BY timestamp ASC
LIMIT 5;

-- Test 8: Large content handling
SELECT 
    uuid,
    LENGTH(message_content) as content_length,
    CASE 
        WHEN LENGTH(message_content) > 1000 THEN 'LARGE'
        WHEN LENGTH(message_content) > 100 THEN 'MEDIUM'
        ELSE 'SMALL'
    END as size_category
FROM read_claude_conversations('test/data')
WHERE message_content IS NOT NULL;

-- Test 9: UUID format validation
SELECT uuid
FROM read_claude_conversations('test/data')
WHERE uuid SIMILAR TO '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
LIMIT 5;

-- Test 10: Project path patterns
SELECT DISTINCT project
FROM read_claude_conversations('test/data')
WHERE project LIKE '%testuser%';

-- ============================================
-- Aggregation Tests
-- ============================================

-- Test 11: Messages per session
SELECT 
    session_id,
    COUNT(*) as messages
FROM read_claude_conversations('test/data')
WHERE session_id IS NOT NULL
GROUP BY session_id
ORDER BY messages DESC
LIMIT 5;

-- Test 12: Tool usage frequency
SELECT 
    tool_name,
    COUNT(*) as usage_count
FROM read_claude_conversations('test/data')
WHERE tool_name IS NOT NULL
GROUP BY tool_name
ORDER BY usage_count DESC;

-- ============================================
-- Summary Stats
-- ============================================

-- Test 13: Overall summary
SELECT 
    (SELECT COUNT(*) FROM read_claude_conversations('test/data')) as total_messages,
    (SELECT COUNT(*) FROM read_claude_plans('test/data')) as total_plans,
    (SELECT COUNT(*) FROM read_claude_todos('test/data')) as total_todos,
    (SELECT COUNT(*) FROM read_claude_history('test/data')) as total_history;
