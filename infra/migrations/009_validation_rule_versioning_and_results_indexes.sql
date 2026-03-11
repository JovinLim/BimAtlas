-- Migration 009: Validation rule versioning and IfcValidationResults indexes
-- Adds version lifecycle to validation_rule (edit = insert new version, deactivate old).
-- Adds partial GIN and btree indexes for IfcValidationResults entity lookups.

-- 1) validation_rule: add version and logical_rule_id for edit-as-insert lifecycle
ALTER TABLE validation_rule
  ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS logical_rule_id UUID;

-- Backfill: existing rows get logical_rule_id = rule_id (each is its own logical rule)
UPDATE validation_rule
SET logical_rule_id = rule_id
WHERE logical_rule_id IS NULL;

-- Trigger: set logical_rule_id = rule_id when null (new rules are their own logical root)
CREATE OR REPLACE FUNCTION set_validation_rule_logical_id()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.logical_rule_id IS NULL THEN
    NEW.logical_rule_id := NEW.rule_id;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tr_validation_rule_logical_id ON validation_rule;
CREATE TRIGGER tr_validation_rule_logical_id
  BEFORE INSERT ON validation_rule
  FOR EACH ROW
  EXECUTE FUNCTION set_validation_rule_logical_id();

-- Unique: one (logical_rule_id, version) pair per row (allows multiple versions)
CREATE UNIQUE INDEX IF NOT EXISTS idx_validation_rule_logical_version
  ON validation_rule (logical_rule_id, version)
  WHERE logical_rule_id IS NOT NULL;

-- Partial unique: exactly one active row per logical rule
CREATE UNIQUE INDEX IF NOT EXISTS idx_validation_rule_active_per_logical
  ON validation_rule (logical_rule_id)
  WHERE is_active = TRUE AND logical_rule_id IS NOT NULL;

-- 2) Partial GIN index for IfcValidationResults JSONB attributes
CREATE INDEX IF NOT EXISTS idx_ifc_entity_validation_attrs_gin
  ON ifc_entity USING GIN (attributes jsonb_path_ops)
  WHERE ifc_class = 'IfcValidationResults' AND obsoleted_in_revision_id IS NULL;

-- 3) Btree index for run-scoped lookups (branch, revision, schema, rule)
CREATE INDEX IF NOT EXISTS idx_ifc_entity_validation_run
  ON ifc_entity (
    branch_id,
    ((attributes->>'TargetRevisionSeq')::int),
    (attributes->>'SchemaGlobalId'),
    (attributes->>'rule_id')
  )
  WHERE ifc_class = 'IfcValidationResults' AND obsoleted_in_revision_id IS NULL;
