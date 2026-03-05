# Hard Constraints

- Validation entities (IfcValidation, IfcValidationSchema, IfcValidationResult) must be stored in the unified `ifc_entity` table as rows with `ifc_class` set accordingly—not in the existing `validation_rule` table, which is reserved for IFC schema metadata (inheritance trees, required attributes).
- All Cypher queries for subgraph validation must use the `_validate_id`, `_validate_label`, and `_escape_cypher_string` sanitization functions from `age_client.py`. Never embed raw user input into Cypher strings.
- Validation entities follow the same SCD Type 2 versioning as all other entities: changes create new rows with `created_in_revision_id`, and old rows are closed with `obsoleted_in_revision_id`.
- Graph edges (IfcRelValidationToSchema) must carry `branch_id`, `valid_from_rev`, and `valid_to_rev` properties matching the standard node/edge versioning pattern.

# Resolved Pitfalls

- (None yet — feature planning phase)
