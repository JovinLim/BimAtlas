-- Migration 013: Add active column to ifc_schema for soft delete
--
-- Schemas are flagged as deleted (active = false) instead of being removed.
-- Listing and validation only consider active schemas.

ALTER TABLE ifc_schema ADD COLUMN IF NOT EXISTS active BOOLEAN NOT NULL DEFAULT TRUE;
