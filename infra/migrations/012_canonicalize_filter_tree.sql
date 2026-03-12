-- Migration 012: Canonicalize filter_sets.filters to tree shape
--
-- Converts legacy flat arrays to canonical tree:
--   { "kind": "group", "op": "ALL"|"ANY", "children": [ { "kind": "leaf", ... }, ... ] }
--
-- Only affects rows where filters is a JSON array (legacy format).
-- Safe to re-run: idempotent (skips rows already in tree format).
-- No schema change; filters column remains JSONB.

BEGIN;

UPDATE filter_sets
SET filters = jsonb_build_object(
  'kind', 'group',
  'op', CASE WHEN logic::text = 'OR' THEN 'ANY' ELSE 'ALL' END,
  'children', COALESCE(
    (
      SELECT jsonb_agg(elem || jsonb_build_object('kind', 'leaf'))
      FROM jsonb_array_elements(filters) AS elem
      WHERE jsonb_typeof(elem) = 'object' AND elem ? 'mode'
    ),
    '[]'::jsonb
  )
)
WHERE jsonb_typeof(filters) = 'array';

COMMIT;
