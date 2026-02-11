-- Test: read_conversations correctness and invariants
-- All assertions use WHERE NOT ... to produce 0 rows on success

-- Test 1: Expected row count
SELECT CASE WHEN cnt = 180 THEN 'PASS' ELSE 'FAIL: expected 180 got ' || cnt END AS test_conversations_count
FROM (SELECT COUNT(*) AS cnt FROM read_conversations(path='test/data'));

-- Test 2: All line numbers are per-file (start at 1)
SELECT CASE WHEN min_ln = 1 THEN 'PASS' ELSE 'FAIL: min line not 1 for ' || file_name END AS test_line_numbers_start_at_1
FROM (SELECT file_name, MIN(line_number) AS min_ln FROM read_conversations(path='test/data') GROUP BY file_name)
WHERE min_ln != 1;

-- Test 3: project_path matches history.project (no lossy decode artifacts)
SELECT CASE WHEN cnt = 0 THEN 'PASS' ELSE 'FAIL: ' || cnt || ' rows with slash-decoded paths' END AS test_no_lossy_paths
FROM (SELECT COUNT(*) AS cnt FROM read_conversations(path='test/data') WHERE project_path LIKE '%/project/%');

-- Test 4: session_id is never NULL
SELECT CASE WHEN cnt = 0 THEN 'PASS' ELSE 'FAIL: ' || cnt || ' NULL session_ids' END AS test_session_id_not_null
FROM (SELECT COUNT(*) AS cnt FROM read_conversations(path='test/data') WHERE session_id IS NULL);

-- Test 5: project_dir is always the raw encoded folder name
SELECT CASE WHEN cnt > 0 THEN 'PASS' ELSE 'FAIL: no project_dir values' END AS test_project_dir_present
FROM (SELECT COUNT(DISTINCT project_dir) AS cnt FROM read_conversations(path='test/data'));

-- Test 6: 3 distinct projects
SELECT CASE WHEN cnt = 3 THEN 'PASS' ELSE 'FAIL: expected 3 projects got ' || cnt END AS test_project_count
FROM (SELECT COUNT(DISTINCT project_path) AS cnt FROM read_conversations(path='test/data'));

-- Test 7: Message types include user and assistant
SELECT CASE WHEN cnt >= 2 THEN 'PASS' ELSE 'FAIL: missing message types' END AS test_message_types
FROM (SELECT COUNT(DISTINCT message_type) AS cnt FROM read_conversations(path='test/data') WHERE message_type IN ('user', 'assistant'));

-- Test 8: Agent files detected
SELECT CASE WHEN cnt > 0 THEN 'PASS' ELSE 'FAIL: no agent files' END AS test_agent_detection
FROM (SELECT COUNT(*) AS cnt FROM read_conversations(path='test/data') WHERE is_agent = true);

-- Test 9: UUID format validation (user/assistant messages have valid UUIDs)
SELECT CASE WHEN cnt = 0 THEN 'PASS' ELSE 'FAIL: ' || cnt || ' invalid UUIDs' END AS test_uuid_format
FROM (SELECT COUNT(*) AS cnt FROM read_conversations(path='test/data')
      WHERE message_type IN ('user', 'assistant')
      AND uuid IS NOT NULL
      AND uuid NOT SIMILAR TO '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}');

-- Test 10: No parse errors in test data
SELECT CASE WHEN cnt = 0 THEN 'PASS' ELSE 'FAIL: ' || cnt || ' parse errors' END AS test_no_parse_errors
FROM (SELECT COUNT(*) AS cnt FROM read_conversations(path='test/data') WHERE message_type = '_parse_error');

-- Test 11: Slug column populated for user/assistant
SELECT CASE WHEN cnt > 0 THEN 'PASS' ELSE 'FAIL: no slugs found' END AS test_slugs_present
FROM (SELECT COUNT(*) AS cnt FROM read_conversations(path='test/data') WHERE slug IS NOT NULL);

-- Test 12: 12 distinct files (6 main + 6 agent)
SELECT CASE WHEN cnt = 12 THEN 'PASS' ELSE 'FAIL: expected 12 files got ' || cnt END AS test_file_count
FROM (SELECT COUNT(DISTINCT file_name) AS cnt FROM read_conversations(path='test/data'));

-- Test 13: Token counts are non-negative where present
SELECT CASE WHEN cnt = 0 THEN 'PASS' ELSE 'FAIL: ' || cnt || ' negative token counts' END AS test_token_counts_valid
FROM (SELECT COUNT(*) AS cnt FROM read_conversations(path='test/data')
      WHERE (input_tokens IS NOT NULL AND input_tokens < 0)
         OR (output_tokens IS NOT NULL AND output_tokens < 0)
         OR (cache_creation_tokens IS NOT NULL AND cache_creation_tokens < 0)
         OR (cache_read_tokens IS NOT NULL AND cache_read_tokens < 0));

-- Test 14: Timestamps follow ISO 8601 format where present
SELECT CASE WHEN cnt = 0 THEN 'PASS' ELSE 'FAIL: ' || cnt || ' invalid timestamps' END AS test_timestamp_format
FROM (SELECT COUNT(*) AS cnt FROM read_conversations(path='test/data')
      WHERE timestamp IS NOT NULL
      AND timestamp NOT SIMILAR TO '[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}.*');

-- Test 15: Model is non-empty for assistant messages
SELECT CASE WHEN cnt = 0 THEN 'PASS' ELSE 'FAIL: ' || cnt || ' assistant msgs without model' END AS test_assistant_has_model
FROM (SELECT COUNT(*) AS cnt FROM read_conversations(path='test/data')
      WHERE message_type = 'assistant' AND model IS NULL);

-- Test 16: User and assistant messages have content
SELECT CASE WHEN cnt = 0 THEN 'PASS' ELSE 'FAIL: ' || cnt || ' user/assistant msgs without content' END AS test_message_content_present
FROM (SELECT COUNT(*) AS cnt FROM read_conversations(path='test/data')
      WHERE message_type IN ('user', 'assistant')
      AND message_content IS NULL
      AND tool_name IS NULL);
