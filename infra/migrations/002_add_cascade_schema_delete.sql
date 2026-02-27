-- Add ON DELETE CASCADE so deleting an ifc_schema row automatically
-- removes its validation_rule rows (fixes FK violation when deleting schemas).

ALTER TABLE validation_rule DROP CONSTRAINT IF EXISTS validation_rule_schema_id_fkey;
ALTER TABLE validation_rule ADD CONSTRAINT validation_rule_schema_id_fkey
    FOREIGN KEY (schema_id) REFERENCES ifc_schema(schema_id) ON DELETE CASCADE;
