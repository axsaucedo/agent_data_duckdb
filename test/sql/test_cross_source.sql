-- Test: Cross-source queries — UNION, filtering, join isolation

-- Test 1: UNION ALL conversations from both sources
SELECT CASE WHEN cnt = 233 THEN 'PASS' ELSE 'FAIL: expected 233 got ' || cnt END AS test_cross_union_conversations
FROM (SELECT COUNT(*) AS cnt FROM (
    SELECT * FROM read_conversations(path='test/data')
    UNION ALL
    SELECT * FROM read_conversations(path='test/data_copilot')
));

-- Test 2: Source filter works in UNION
SELECT CASE WHEN claude_cnt = 180 AND copilot_cnt = 53 THEN 'PASS'
       ELSE 'FAIL: claude=' || claude_cnt || ' copilot=' || copilot_cnt END AS test_cross_source_filter
FROM (
    SELECT
        SUM(CASE WHEN source = 'claude' THEN 1 ELSE 0 END) AS claude_cnt,
        SUM(CASE WHEN source = 'copilot' THEN 1 ELSE 0 END) AS copilot_cnt
    FROM (
        SELECT * FROM read_conversations(path='test/data')
        UNION ALL
        SELECT * FROM read_conversations(path='test/data_copilot')
    )
);

-- Test 3: UNION ALL plans from both sources
SELECT CASE WHEN cnt = 5 THEN 'PASS' ELSE 'FAIL: expected 5 got ' || cnt END AS test_cross_union_plans
FROM (SELECT COUNT(*) AS cnt FROM (
    SELECT * FROM read_plans(path='test/data')
    UNION ALL
    SELECT * FROM read_plans(path='test/data_copilot')
));

-- Test 4: UNION ALL history from both sources
SELECT CASE WHEN cnt = 25 THEN 'PASS' ELSE 'FAIL: expected 25 got ' || cnt END AS test_cross_union_history
FROM (SELECT COUNT(*) AS cnt FROM (
    SELECT * FROM read_history(path='test/data')
    UNION ALL
    SELECT * FROM read_history(path='test/data_copilot')
));

-- Test 5: UNION ALL todos from both sources
SELECT CASE WHEN cnt = 22 THEN 'PASS' ELSE 'FAIL: expected 22 got ' || cnt END AS test_cross_union_todos
FROM (SELECT COUNT(*) AS cnt FROM (
    SELECT * FROM read_todos(path='test/data')
    UNION ALL
    SELECT * FROM read_todos(path='test/data_copilot')
));

-- Test 6: Session IDs are distinct across sources (no accidental collision)
SELECT CASE WHEN overlap = 0 THEN 'PASS' ELSE 'FAIL: ' || overlap || ' overlapping session_ids' END AS test_cross_session_isolation
FROM (
    SELECT COUNT(*) AS overlap FROM (
        SELECT DISTINCT session_id FROM read_conversations(path='test/data') WHERE session_id != ''
        INTERSECT
        SELECT DISTINCT session_id FROM read_conversations(path='test/data_copilot') WHERE session_id != ''
    )
);

-- Test 7: message_type values are provider-appropriate (copilot has session_start, claude doesn't)
SELECT CASE WHEN cnt > 0 THEN 'PASS' ELSE 'FAIL: no copilot-specific types in union' END AS test_cross_copilot_types_present
FROM (
    SELECT COUNT(*) AS cnt FROM (
        SELECT * FROM read_conversations(path='test/data')
        UNION ALL
        SELECT * FROM read_conversations(path='test/data_copilot')
    ) WHERE message_type = 'session_start'
);

-- Test 8: Claude-specific columns NULL for copilot data
SELECT CASE WHEN cnt = 0 THEN 'PASS' ELSE 'FAIL: ' || cnt || ' copilot rows with slug' END AS test_cross_copilot_null_slug
FROM (SELECT COUNT(*) AS cnt FROM read_conversations(path='test/data_copilot') WHERE slug IS NOT NULL);

-- Test 9: Repository column populated for copilot, NULL for claude
SELECT CASE WHEN copilot_repo > 0 AND claude_repo = 0 THEN 'PASS'
       ELSE 'FAIL: copilot_repo=' || copilot_repo || ' claude_repo=' || claude_repo END AS test_cross_repository_isolation
FROM (
    SELECT
        (SELECT COUNT(*) FROM read_conversations(path='test/data_copilot') WHERE repository IS NOT NULL) AS copilot_repo,
        (SELECT COUNT(*) FROM read_conversations(path='test/data') WHERE repository IS NOT NULL) AS claude_repo
);

-- Test 10: Group by source across tables
SELECT CASE WHEN cnt = 2 THEN 'PASS' ELSE 'FAIL: expected 2 sources got ' || cnt END AS test_cross_source_group_by
FROM (
    SELECT COUNT(DISTINCT source) AS cnt FROM (
        SELECT source FROM read_conversations(path='test/data')
        UNION ALL
        SELECT source FROM read_conversations(path='test/data_copilot')
    )
);
