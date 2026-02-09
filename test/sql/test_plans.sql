-- Test: read_claude_plans basic functionality
-- This file tests the plans table function

-- Test 1: List all plans
SELECT plan_name, file_size, slug
FROM read_claude_plans('test/data/')
ORDER BY plan_name;

-- Test 2: Count total plans
SELECT COUNT(*) as total_plans
FROM read_claude_plans('test/data/');

-- Test 3: Get plan content
SELECT plan_name, LENGTH(content) as content_length
FROM read_claude_plans('test/data/')
ORDER BY content_length DESC;

-- Test 4: Search plans by name pattern
SELECT plan_name, slug
FROM read_claude_plans('test/data/')
WHERE plan_name LIKE '%exploring%' OR plan_name LIKE '%juggling%';

-- Test 5: Get plans with their slugs
SELECT plan_name, slug, file_size
FROM read_claude_plans('test/data/')
WHERE slug IS NOT NULL;

-- Test 6: Plan content contains specific text
SELECT plan_name, content
FROM read_claude_plans('test/data/')
WHERE content LIKE '%Implementation%'
LIMIT 3;

-- Test 7: Plans ordered by size
SELECT plan_name, file_size
FROM read_claude_plans('test/data/')
ORDER BY file_size DESC;
