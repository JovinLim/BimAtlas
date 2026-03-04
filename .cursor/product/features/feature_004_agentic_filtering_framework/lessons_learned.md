# Hard Constraints

- All IDs (project_id, branch_id, revision_id, filter_set_id) are UUID strings; all new code must treat IDs as strings and query attributes via JSONB operators.
- IFC geometry is stored as a single `geometry BYTEA` blob on `ifc_entity`; MCP tools and agent must never expose or process geometry data.
- The `inherits_from` class operator depends on `get_descendants()` which loads IFC hierarchy from `validation_rule` via `fetch_validation_rules`. If the schema is not seeded, `inherits_from` returns no matches. Tests using `inherits_from` must use the `ifc_schema_seeded` fixture.
- LLM API keys must never be stored on the backend or in the database. Keys are provided per-session from the frontend and passed through to the LLM provider.
- MCP tools must wrap existing DB functions (db.py), not duplicate their logic. The filter engine, operator validation, and JSONB translation are already implemented.
- Nested JSONB key filtering uses a recursive JSONB walk in SQL; attribute keys can target keys at any depth (e.g., `PropertySets.PsetWallCommon.FireRating`).

# Resolved Pitfalls

(None yet — to be populated during execution.)
