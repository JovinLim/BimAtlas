-- Migration: Add project-scoped sheet_template table for bottom-sheet table state.
-- Run this on existing databases. New setups use init-age.sql which already has the schema.

CREATE TABLE IF NOT EXISTS sheet_template (
    sheet_template_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id        UUID NOT NULL REFERENCES project(project_id) ON DELETE CASCADE,
    name              VARCHAR NOT NULL,
    sheet             JSONB NOT NULL DEFAULT '{}',
    created_at        TIMESTAMPTZ DEFAULT now(),
    updated_at        TIMESTAMPTZ DEFAULT now(),
    UNIQUE (project_id, name)
);

CREATE INDEX IF NOT EXISTS idx_sheet_template_project ON sheet_template (project_id);
