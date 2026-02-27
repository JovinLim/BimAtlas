-- Migration: Remove project.default_schema_id and add project_schema junction.
-- Run this on existing databases that have the old project table.
-- New setups use init-age.sql which already has the correct schema.

-- Drop FK and column (order matters: drop FK first if it exists)
ALTER TABLE project DROP COLUMN IF EXISTS default_schema_id;

-- Create junction table for many-to-many project <-> ifc_schema
CREATE TABLE IF NOT EXISTS project_schema (
    project_id UUID NOT NULL REFERENCES project(project_id) ON DELETE CASCADE,
    schema_id  UUID NOT NULL REFERENCES ifc_schema(schema_id) ON DELETE CASCADE,
    PRIMARY KEY (project_id, schema_id)
);
