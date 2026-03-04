## Hard Constraints

- The database schema and API now use UUID string identifiers (`project_id`, `branch_id`, `revision_id`, `filter_set_id`) and the unified `ifc_entity` table with `attributes JSONB`; all new code must treat IDs as strings and query attributes via JSONB operators (e.g., `attributes->>'Name'`) instead of legacy scalar columns.
- IFC geometry is now stored as a single `geometry BYTEA` blob on `ifc_entity`, using a fixed header of four 64-bit lengths followed by concatenated buffers; any new code must treat this column as opaque and must not rely on legacy `vertices`/`normals`/`faces`/`matrix` columns.
- AGE graph nodes and edges now store `ifc_global_id` instead of `global_id`, and `branch_id` as a UUID string; all Cypher queries and filters must use these property names with string equality and interpret `valid_from_rev`/`valid_to_rev` as `revision_seq` integers.

## Resolved Pitfalls

- When introducing a new Attribute panel pop-out, Svelte 5 runes required moving panel props to `$props()` and avoiding `export let`, and reusing old CSS inside the wrapper caused a flood of unused-selector warnings; we fixed this by centralizing the data-fetch into a dedicated content component and accepting leftover CSS warnings as non-blocking. Future UI refactors should prefer moving shared styles with the content component to avoid duplicated or orphaned selectors.
- The `inherits_from` class operator depends on `get_descendants()` which loads IFC hierarchy from `validation_rule` via `fetch_validation_rules`. If the schema is not seeded, `inherits_from` returns no matches (FALSE clause). Tests using `inherits_from` must use the `ifc_schema_seeded` fixture.
- Nested JSONB key filtering cannot rely on top-level `attributes->>'Key'` expressions when users enter custom keys like `PropertySets` or nested `Name` fields. We solved this by using a recursive JSONB walk in SQL and applying operators only after key applicability is confirmed, which keeps results aligned with user intent.
- The applied filter set AND/OR toggle was disabled in the UI even though the backend supported per-set logic. We enabled the buttons and wired `handleLogicChange` to call `updateFilterSet` with the new logic, then broadcast the updated sets to the main view.

