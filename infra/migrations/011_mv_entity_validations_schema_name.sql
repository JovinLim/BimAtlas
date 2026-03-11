-- Migration 011: Add schemaName to mv_entity_validations output for attribute panel display.
-- Drops and recreates the MV to include SchemaName from IfcValidationResults.

DROP MATERIALIZED VIEW IF EXISTS mv_entity_validations;

CREATE MATERIALIZED VIEW mv_entity_validations AS
WITH validation_rows AS (
  SELECT
    e.branch_id,
    (e.attributes->>'TargetRevisionSeq')::int AS revision_seq,
    e.attributes->>'rule_id' AS rule_id,
    COALESCE((e.attributes->>'rule_version')::int, 1) AS rule_version,
    vr.name AS rule_name,
    vr.severity::text AS severity,
    e.attributes->>'SchemaName' AS schema_name,
    jsonb_array_elements_text(COALESCE(e.attributes->'results'->'failed_global_ids', '[]'::jsonb)) AS entity_global_id,
    false AS passed,
    CASE WHEN COALESCE((e.attributes->>'rule_version')::int, 1) = vr.version THEN 'fresh' ELSE 'stale' END AS status
  FROM ifc_entity e
  JOIN validation_rule vr
    ON vr.rule_id::text = e.attributes->>'rule_id'
   AND vr.is_active = true
  WHERE e.ifc_class = 'IfcValidationResults'
    AND e.obsoleted_in_revision_id IS NULL

  UNION ALL

  SELECT
    e.branch_id,
    (e.attributes->>'TargetRevisionSeq')::int AS revision_seq,
    e.attributes->>'rule_id' AS rule_id,
    COALESCE((e.attributes->>'rule_version')::int, 1) AS rule_version,
    vr.name AS rule_name,
    vr.severity::text AS severity,
    e.attributes->>'SchemaName' AS schema_name,
    jsonb_array_elements_text(COALESCE(e.attributes->'results'->'passed_global_ids', '[]'::jsonb)) AS entity_global_id,
    true AS passed,
    CASE WHEN COALESCE((e.attributes->>'rule_version')::int, 1) = vr.version THEN 'fresh' ELSE 'stale' END AS status
  FROM ifc_entity e
  JOIN validation_rule vr
    ON vr.rule_id::text = e.attributes->>'rule_id'
   AND vr.is_active = true
  WHERE e.ifc_class = 'IfcValidationResults'
    AND e.obsoleted_in_revision_id IS NULL
)
SELECT
  branch_id,
  revision_seq,
  entity_global_id,
  jsonb_object_agg(
    rule_id,
    jsonb_build_object(
      'ruleName', rule_name,
      'severity', severity,
      'passed', passed,
      'status', status,
      'schemaName', schema_name
    )
  ) AS validations
FROM validation_rows
GROUP BY branch_id, revision_seq, entity_global_id;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_entity_validations_key
  ON mv_entity_validations (branch_id, revision_seq, entity_global_id);
