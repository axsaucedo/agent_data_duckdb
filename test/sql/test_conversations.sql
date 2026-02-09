-- Test: read_claude_conversations basic functionality
-- This file tests the conversations table function

-- Test 1: Basic query - should return all messages
SELECT COUNT(*) as total_messages 
FROM read_claude_conversations('test/data/');

-- Test 2: Filter by message type
SELECT message_type, COUNT(*) as count 
FROM read_claude_conversations('test/data/')
GROUP BY message_type
ORDER BY count DESC;

-- Test 3: Get messages for a specific session
SELECT session_id, message_uuid, message_type, timestamp
FROM read_claude_conversations('test/data/')
WHERE session_id IS NOT NULL
LIMIT 10;

-- Test 4: Get user messages with content
SELECT session_id, timestamp, content
FROM read_claude_conversations('test/data/')
WHERE message_type = 'user'
LIMIT 5;

-- Test 5: Get assistant messages with tool usage
SELECT session_id, timestamp, tool_uses
FROM read_claude_conversations('test/data/')
WHERE message_type = 'assistant' 
  AND tool_uses IS NOT NULL
  AND json_array_length(tool_uses) > 0
LIMIT 5;

-- Test 6: Get messages by project
SELECT project_path, COUNT(*) as message_count
FROM read_claude_conversations('test/data/')
GROUP BY project_path
ORDER BY message_count DESC;

-- Test 7: Get message threading (parent-child relationships)
SELECT 
    c1.message_uuid,
    c1.message_type,
    c2.message_uuid as parent_uuid,
    c2.message_type as parent_type
FROM read_claude_conversations('test/data/') c1
LEFT JOIN read_claude_conversations('test/data/') c2 
    ON c1.parent_uuid = c2.message_uuid
WHERE c1.parent_uuid IS NOT NULL
LIMIT 10;

-- Test 8: Token usage statistics
SELECT 
    session_id,
    SUM(json_extract(token_usage, '$.input_tokens')::INTEGER) as total_input_tokens,
    SUM(json_extract(token_usage, '$.output_tokens')::INTEGER) as total_output_tokens
FROM read_claude_conversations('test/data/')
WHERE message_type = 'assistant'
GROUP BY session_id;

-- Test 9: Messages ordered by timestamp
SELECT message_type, timestamp, content
FROM read_claude_conversations('test/data/')
WHERE message_type IN ('user', 'assistant')
ORDER BY timestamp
LIMIT 10;

-- Test 10: Get agent messages (sub-agent conversations)
SELECT session_id, message_uuid, timestamp
FROM read_claude_conversations('test/data/')
WHERE session_id LIKE '%agent%' OR project_path LIKE '%agent%'
LIMIT 5;
