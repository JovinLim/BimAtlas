-- Migration 006: Validation entity AGE labels and partial index
-- Creates vertex/edge labels for IfcValidation, IfcValidationSchema,
-- IfcValidationResult, and IfcRelValidationToSchema.

LOAD 'age';
SET search_path = ag_catalog, "$user", public;

DO $$
DECLARE
    g_oid oid;
BEGIN
    SELECT graphid INTO g_oid FROM ag_catalog.ag_graph WHERE name = 'bimatlas';
    IF g_oid IS NULL THEN
        RAISE NOTICE 'Graph bimatlas not found — skipping label creation';
        RETURN;
    END IF;

    -- Vertex labels
    IF NOT EXISTS (SELECT 1 FROM ag_catalog.ag_label WHERE name = 'IfcValidation' AND graph = g_oid AND kind = 'v') THEN
        PERFORM create_vlabel('bimatlas', 'IfcValidation');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM ag_catalog.ag_label WHERE name = 'IfcValidationSchema' AND graph = g_oid AND kind = 'v') THEN
        PERFORM create_vlabel('bimatlas', 'IfcValidationSchema');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM ag_catalog.ag_label WHERE name = 'IfcValidationResult' AND graph = g_oid AND kind = 'v') THEN
        PERFORM create_vlabel('bimatlas', 'IfcValidationResult');
    END IF;

    -- Edge label
    IF NOT EXISTS (SELECT 1 FROM ag_catalog.ag_label WHERE name = 'IfcRelValidationToSchema' AND graph = g_oid AND kind = 'e') THEN
        PERFORM create_elabel('bimatlas', 'IfcRelValidationToSchema');
    END IF;
END $$;

-- Partial index for fast validation entity lookups
CREATE INDEX IF NOT EXISTS idx_ifc_entity_validation_class
    ON ifc_entity (branch_id, ifc_class)
    WHERE ifc_class IN ('IfcValidation', 'IfcValidationSchema', 'IfcValidationResult')
      AND obsoleted_in_revision_id IS NULL;
