-- Migration: Add open column to sheet_template table.
-- Run this on existing databases that have sheet_template from 003.

ALTER TABLE sheet_template ADD COLUMN IF NOT EXISTS open BOOLEAN NOT NULL DEFAULT FALSE;
