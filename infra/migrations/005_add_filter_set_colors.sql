-- Migration 001: Add filter set colors and display ordering
--
-- Adds:
--   filter_sets.color              – hex color for viewer coloring
--   branch_applied_filter_sets.display_order – ordering for color priority
--
-- Safe to re-run: uses IF NOT EXISTS / ADD COLUMN IF NOT EXISTS.
-- Requires PostgreSQL 9.6+ for ADD COLUMN IF NOT EXISTS.

BEGIN;

-- 1. Add color column to filter_sets (default blue for existing rows)
ALTER TABLE filter_sets
    ADD COLUMN IF NOT EXISTS color VARCHAR NOT NULL DEFAULT '#4A90D9';

-- 2. Add display_order column to branch_applied_filter_sets
--    Existing applied sets get order 0; the apply_filter_sets() function
--    now writes sequential integers when (re-)applying sets.
ALTER TABLE branch_applied_filter_sets
    ADD COLUMN IF NOT EXISTS display_order INTEGER NOT NULL DEFAULT 0;

COMMIT;
