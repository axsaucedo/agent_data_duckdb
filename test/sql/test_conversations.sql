-- Test: read_claude_conversations basic functionality
-- This file tests the conversations table function

-- Test 1: Basic query - should return all messages
SELECT COUNT(*) as total_messages 
FROM read_claude_conversations('test/data');

-- Test 2: Filter by message role
SELECT message_role, COUNT(*) as count 
FROM read_claude_conversations('test/data')
WHERE message_role IS NOT NULL
GROUP BY message_role
ORDER BY count DESC;

-- Test 3: Get messages for a specific session
SELECT session_id, uuid, type, timestamp
FROM read_claude_conversations('test/data')
WHERE session_id IS NOT NULL
LIMIT 10;

-- Test 4: Get user messages with content
SELECT session_id, timestamp, message_content
FROM read_claude_conversations('test/data')
WHERE message_role = 'user'
LIMIT 5;

-- Test 5: Get assistant messages with tool usage
SELECT session_id, timestamp, tool_name, tool_input
FROM read_claude_conversations('test/data')
WHERE message_role = 'assistant' 
  AND tool_name IS NOT NULL
LIMIT 5;

-- Test 6: Get messages by project
SELECT project, COUNT(*) as message_count
FROM read_claude_conversations('test/data')
GROUP BY project
ORDER BY message_count DESC;

-- Test 7: Get message threading (parent-child relationships)
SELECT 
    c1.uuid,
    c1.type,
    c2.uuid as parent_uuid_match,
    c2.type as parent_type
FROM read_claude_conversations('test/data') c1
LEFT JOIN read_claude_conversations('test/data') c2 
    ON c1.parent_uuid = c2.uuid
WHERE c1.parent_uuid IS NOT NULL
LIMIT 10;

-- Test 8: Tool usage statistics
SELECT 
    session_id,
    tool_name,
    COUNT(*) as usage_count
FROM read_claude_conversations('test/data')
WHERE tool_name IS NOT NULL
GROUP BY session_id, tool_name
ORDER BY usage_count DESC
LIMIT 10;

-- Test 9: Messages ordered by timestamp
SELECT type, timestamp, message_content
FROM read_claude_conversations('test/data')
WHERE type IN ('user', 'assistant')
ORDER BY timestamp
LIMIT 10;

-- Test 10: Get agent messages (sub-agent conversations)
SELECT session_id, uuid, timestamp
FROM read_claude_conversations('test/data')
WHERE is_agent = TRUE
LIMIT 5;
