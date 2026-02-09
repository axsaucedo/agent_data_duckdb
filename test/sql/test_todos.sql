-- Test: read_claude_todos basic functionality
-- This file tests the todos table function

-- Test 1: List all todos
SELECT session_id, agent_id, content, status
FROM read_claude_todos('test/data/')
ORDER BY session_id, todo_index;

-- Test 2: Count todos by status
SELECT status, COUNT(*) as count
FROM read_claude_todos('test/data/')
GROUP BY status
ORDER BY count DESC;

-- Test 3: Get completed todos
SELECT session_id, content, active_form
FROM read_claude_todos('test/data/')
WHERE status = 'completed';

-- Test 4: Get in-progress todos
SELECT session_id, content, active_form
FROM read_claude_todos('test/data/')
WHERE status = 'in_progress';

-- Test 5: Get pending todos
SELECT session_id, content, active_form
FROM read_claude_todos('test/data/')
WHERE status = 'pending';

-- Test 6: Todos per session
SELECT session_id, COUNT(*) as todo_count
FROM read_claude_todos('test/data/')
GROUP BY session_id
ORDER BY todo_count DESC;

-- Test 7: Search todos by content
SELECT session_id, content, status
FROM read_claude_todos('test/data/')
WHERE content LIKE '%Task%';

-- Test 8: Todos with active form set
SELECT session_id, content, active_form
FROM read_claude_todos('test/data/')
WHERE active_form IS NOT NULL AND active_form != '';
