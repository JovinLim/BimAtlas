## Hard Constraints

- The database schema and API now use UUID string identifiers (`project_id`, `branch_id`, `revision_id`, `filter_set_id`) and the unified `ifc_entity` table with `attributes JSONB`; all new code must treat IDs as strings and query attributes via JSONB operators (e.g., `attributes->>'Name'`) instead of legacy scalar columns.
- IFC geometry is now stored as a single `geometry BYTEA` blob on `ifc_entity`, using a fixed header of four 64-bit lengths followed by concatenated buffers; any new code must treat this column as opaque and must not rely on legacy `vertices`/`normals`/`faces`/`matrix` columns.
- AGE graph nodes and edges now store `ifc_global_id` instead of `global_id`, and `branch_id` as a UUID string; all Cypher queries and filters must use these property names with string equality and interpret `valid_from_rev`/`valid_to_rev` as `revision_seq` integers.

## Resolved Pitfalls

- When introducing a new Attribute panel pop-out, Svelte 5 runes required moving panel props to `$props()` and avoiding `export let`, and reusing old CSS inside the wrapper caused a flood of unused-selector warnings; we fixed this by centralizing the data-fetch into a dedicated content component and accepting leftover CSS warnings as non-blocking. Future UI refactors should prefer moving shared styles with the content component to avoid duplicated or orphaned selectors.

