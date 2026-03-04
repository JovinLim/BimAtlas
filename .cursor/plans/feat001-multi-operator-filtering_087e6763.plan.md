---
name: feat001-multi-operator-filtering
overview: Expand FEAT-001 filtering from fixed equality/contains behavior to a typed, multi-operator engine with IFC inheritance-aware class matching, while keeping schema changes minimal and preserving SQL safety. Deliver backend/operator translation, GraphQL/frontend contract updates, and regression coverage for string, numeric, emptiness, and inheritance filters.
todos:
  - id: define-operator-contract
    content: Specify canonical operators, per-mode required fields, and backward-compat defaults for legacy filters.
    status: completed
  - id: extend-api-filter-types
    content: Add operator-capable filter fields to GraphQL input/output models and filter-set serialization/hydration.
    status: completed
  - id: refactor-sql-filter-builder
    content: Implement mode-specific, allowlisted, parameterized SQL builders for string/numeric/empty/inheritance operations.
    status: completed
  - id: wire-inheritance-and-query-path
    content: Use IFC schema descendants for inherits_from and align ifcProducts/streaming query paths with shared operator logic.
    status: completed
  - id: update-frontend-editor-contract
    content: Add operator support to frontend filter types, GraphQL fragments, and SearchFilter editor behavior.
    status: completed
  - id: test-and-verify
    content: Add operator matrix tests and run API/frontend validation including applied filter-set end-to-end scenario.
    status: completed
isProject: false
---

# FEAT-001 Multi-Operator Filtering Expansion Plan

## Goal

Implement a robust operator system for filter sets (string, numeric, empty/not-empty, and IFC inheritance) in the existing JSONB-based filter engine, and verify whether DB schema changes are needed (apply only minimal changes if required).

## Current-State Findings (for execution)

- Persisted filter payloads already live in `filter_sets.filters` as JSONB, so new operator metadata can be stored without adding tables/columns.
- Operator execution is currently hardcoded in `_build_filter_clause()` in [apps/api/src/db.py](apps/api/src/db.py) and mainly does class equality + string `ILIKE` contains.
- IFC inheritance helpers already exist via `get_descendants()` in [apps/api/src/schema/ifc_schema_loader.py](apps/api/src/schema/ifc_schema_loader.py).
- GraphQL input/output types for filters are currently narrow (`mode`, `ifcClass`, `attribute`, `value`, `relation`) in [apps/api/src/schema/ifc_types.py](apps/api/src/schema/ifc_types.py), [apps/api/src/schema/queries.py](apps/api/src/schema/queries.py), and [apps/web/src/lib/search/protocol.ts](apps/web/src/lib/search/protocol.ts).
- `ifcProducts` currently calls `fetch_entities_at_revision()` directly in [apps/api/src/schema/queries.py](apps/api/src/schema/queries.py); applied filter sets are handled by separate APIs and may need explicit wiring/alignment depending on chosen query path.

## Implementation Steps

1. **Define canonical operator contract (API + UI shared semantics).**

- Introduce a normalized operator vocabulary and mapping for requested terms:
  - String/logical: `is`, `is_not`, `contains`, `not_contains`, `starts_with`, `ends_with`, `is_empty`, `is_not_empty`
  - Numeric: `equals`, `not_equals`, `gt`, `lt`, `gte`, `lte`
  - IFC class: `inherits_from` (class + descendants)
- Specify per-mode required fields (`attribute`, `value`, optional second value if future range support is desired).
- Preserve backward compatibility by treating missing operator as legacy defaults (`class => is`, `attribute => contains`).

1. **Extend GraphQL and payload serialization for richer filters.**

- Update filter types/inputs in [apps/api/src/schema/ifc_types.py](apps/api/src/schema/ifc_types.py) to include operator metadata (e.g., `operator`, optional `value_type`, optional `inheritance` flag).
- Update create/update mapping and row-to-type hydration in [apps/api/src/schema/queries.py](apps/api/src/schema/queries.py) so new keys round-trip through `filter_sets.filters` JSONB.
- Keep IDs as UUID strings per hard constraint.

1. **Implement operator-aware SQL translation in the filter engine.**

- Refactor `_build_filter_clause()` in [apps/api/src/db.py](apps/api/src/db.py) into mode-specific builders:
  - class builder (exact + inheritance via descendants)
  - attribute string builder (exact/not exact/contains/not contains/prefix/suffix/empty checks)
  - attribute numeric builder (`::numeric` guarded comparisons)
  - relation builder (existing AGE relation path)
- Enforce strict allowlists for logical join tokens (`AND`/`OR`) and operators before assembling SQL fragments.
- Keep all user values parameterized; no raw SQL from user payloads.
- Continue querying only JSONB attributes / `ifc_global_id`; do not touch geometry payload semantics.

1. **Implement IFC inheritance filter behavior using existing schema loader.**

- For class filters with `inherits_from`, resolve descendants through `get_descendants()` in [apps/api/src/schema/ifc_schema_loader.py](apps/api/src/schema/ifc_schema_loader.py).
- Build SQL as `e.ifc_class = ANY(%s)` over resolved class list (include concrete descendants; include self per operator definition).
- Handle unknown classes safely (return no matches or skip based on explicit policy).

1. **Align query execution path so operator filters drive entity retrieval consistently.**

- Decide and implement one canonical path:
  - either wire `ifcProducts` in [apps/api/src/schema/queries.py](apps/api/src/schema/queries.py) through applied filter sets + `fetch_entities_with_filter_sets()`,
  - or keep ad-hoc and saved-set paths separate but ensure both call shared operator builder logic.
- Mirror behavior in streaming path if needed (`apps/api/src/main.py`) to avoid drift between GraphQL and SSE results.

1. **Update frontend filter model and editor for operator selection.**

- Extend filter type in [apps/web/src/lib/search/protocol.ts](apps/web/src/lib/search/protocol.ts) and GraphQL fragments in [apps/web/src/lib/api/client.ts](apps/web/src/lib/api/client.ts) with new operator fields.
- Update editor UI in [apps/web/src/lib/ui/SearchFilter.svelte](apps/web/src/lib/ui/SearchFilter.svelte) and [apps/web/src/routes/search/+page.svelte](apps/web/src/routes/search/+page.svelte):
  - show operator dropdown per mode/attribute type
  - hide value input for `is_empty`/`is_not_empty`
  - enforce numeric input for numeric operators where applicable.
- Preserve existing saved filters by defaulting operator when absent.

1. **Schema decision and minimal-change policy.**

- **Expected outcome:** no schema migration required (JSONB already supports richer payloads).
- Validate in [infra/init-age.sql](infra/init-age.sql) and [apps/api/tests/conftest.py](apps/api/tests/conftest.py) that `filter_sets.filters JSONB` and existing indexes are sufficient.
- Only if absolutely necessary, apply a minimal guard (e.g., lightweight JSON shape check); avoid new tables or broad migrations.

1. **Add/extend tests for operator matrix and inheritance behavior.**

- Expand [apps/api/tests/test_filter_sets.py](apps/api/tests/test_filter_sets.py) with coverage for each operator family:
  - string positive/negative cases
  - numeric comparison/cast failure handling
  - empty/not-empty semantics
  - `inherits_from` returning descendants (e.g., `IfcBuildingElement` includes wall/slab/window)
  - join-logic allowlist hardening.
- Add API-level tests if needed in [apps/api/tests/test_api.py](apps/api/tests/test_api.py) for GraphQL filter I/O.

1. **Verification (final step).**

- Run API tests in project venv (`apps/api/.venv`) with focus on filter suites, then full suite if practical.
- Run frontend type/lint checks for changed filter contracts.
- Validate one end-to-end scenario: create saved filter set with mixed operators, apply to branch, confirm returned entities match expected inheritance + numeric/string logic.

## Constraints to Inject During Execution

- Treat IDs (`project_id`, `branch_id`, `revision_id`, `filter_set_id`) as UUID strings.
- Query IFC attributes through `ifc_entity.attributes` JSONB operators; do not revert to legacy scalar columns.
- Keep geometry handling opaque (`geometry BYTEA` untouched by filtering).
- Maintain AGE property naming expectations where relation filters are involved (`ifc_global_id`, string `branch_id`, revision sequence semantics).
