---
name: entity-formula-columns
overview: Expand the filtered entities table to support user-created top-table columns with entity-path formulas, nested attribute access, header display aliases, and formula-guide updates while preserving existing protected default columns and v1 session-local state.
todos:
  - id: extend-product-attributes-payload
    content: Add attributes JSON to streamed products and shared frontend product/context types.
    status: completed
  - id: dynamic-top-columns-model
    content: Refactor top grid to route-owned default+custom column config with undeletable defaults.
    status: completed
  - id: entity-path-formula-evaluator
    content: Implement =ENTITY.path formula resolution with nested path traversal and null-safe fallback.
    status: completed
  - id: top-header-display-alias-syntax
    content: Support [Display Text](Formula) parsing/editing for top headers only.
    status: completed
  - id: formula-guide-update
    content: Document ENTITY formulas and header alias syntax in formula suggestions/guide overlay.
    status: completed
  - id: playwright-coverage
    content: Expand fixture tests for custom columns, nested attributes, null handling, undeletable defaults, and alias syntax.
    status: completed
  - id: verification
    content: Run web type-check and spreadsheet tests to validate behavior and guard regressions.
    status: completed
isProject: false
---

# Expand Filtered Entities Table: Entity Formula Columns

## Goal

Add user-defined top-table columns after the default IFC columns. Each custom column can be driven by an entity formula like `=ENTITY.Attribute` or `=ENTITY.PropertySets.PsetWallCommon`. Missing paths resolve to `NULL` (rendered as empty). Default IFC columns remain undeletable. Also support header syntax `[Display Text](Formula)` for top headers only, and document it in the formula guide.

## Scope and constraints

- Keep v1 state local/session-only (no backend persistence of table column config).
- Do not alter filtering source-of-truth: table still uses streamed `searchState.products` context.
- Only top entity table headers support `[Display Text](Formula)`; bottom sheet remains unchanged.

## Implementation steps

1. **Extend table product payload to include raw attributes JSON for nested path access.**

- Backend: include `attributes` in stream product payload from `ifc_entity.attributes` with safe JSON handling.
- Frontend: extend shared table/search product type and table-context serialization to carry `attributes`.
- Files:
  - [/home/jovin/projects/BimAtlas/apps/api/src/schema/queries.py](/home/jovin/projects/BimAtlas/apps/api/src/schema/queries.py)
  - [/home/jovin/projects/BimAtlas/apps/web/src/lib/search/protocol.ts](/home/jovin/projects/BimAtlas/apps/web/src/lib/search/protocol.ts)
  - [/home/jovin/projects/BimAtlas/apps/web/src/routes/+page.svelte](/home/jovin/projects/BimAtlas/apps/web/src/routes/+page.svelte)
  - [/home/jovin/projects/BimAtlas/apps/web/src/lib/table/protocol.ts](/home/jovin/projects/BimAtlas/apps/web/src/lib/table/protocol.ts)
  - [/home/jovin/projects/BimAtlas/apps/web/src/lib/table/fixtures.ts](/home/jovin/projects/BimAtlas/apps/web/src/lib/table/fixtures.ts)

1. **Introduce a top-table column model with default protected columns + custom append-only columns.**

- Replace hard-coded top header definitions with a route-owned column config:
  - default columns (existing IFC fields) marked `isDefault: true`, `deletable: false`.
  - custom columns `isDefault: false`, `deletable: true`, inserted after defaults.
- Keep lock/protected-cell behavior intact for default protected fields.
- Files:
  - [/home/jovin/projects/BimAtlas/apps/web/src/routes/table/+page.svelte](/home/jovin/projects/BimAtlas/apps/web/src/routes/table/+page.svelte)
  - [/home/jovin/projects/BimAtlas/apps/web/src/lib/table/EntityGrid.svelte](/home/jovin/projects/BimAtlas/apps/web/src/lib/table/EntityGrid.svelte)
  - [/home/jovin/projects/BimAtlas/apps/web/src/lib/table/engine.ts](/home/jovin/projects/BimAtlas/apps/web/src/lib/table/engine.ts)

1. **Add entity-path formula resolution for custom columns.**

- Extend formula parsing/evaluation utilities to recognize `=ENTITY.<path>` for column formulas.
- Implement safe nested traversal against per-row `product.attributes` (dot-path), returning `null` when any segment is missing.
- Normalize result rendering: `null`/missing -> empty cell display (`""`) to satisfy graceful NULL handling.
- Example supported path: `=ENTITY.PropertySets.PsetWallCommon`.
- Files:
  - [/home/jovin/projects/BimAtlas/apps/web/src/lib/table/formulas.ts](/home/jovin/projects/BimAtlas/apps/web/src/lib/table/formulas.ts)
  - [/home/jovin/projects/BimAtlas/apps/web/src/routes/table/+page.svelte](/home/jovin/projects/BimAtlas/apps/web/src/routes/table/+page.svelte)

1. **Implement top-header formula editing and markdown alias syntax.**

- Add top-header input/edit flow for custom columns.
- Parse `[Display Text](Formula)` as:
  - header label = `Display Text`
  - stored/evaluated formula = `Formula`
- If header input is plain formula (e.g. `=ENTITY.X`), keep existing label fallback.
- Apply parsing only in top header context; do not enable this syntax in body cells or bottom sheet.
- Files:
  - [/home/jovin/projects/BimAtlas/apps/web/src/lib/table/EntityGrid.svelte](/home/jovin/projects/BimAtlas/apps/web/src/lib/table/EntityGrid.svelte)
  - [/home/jovin/projects/BimAtlas/apps/web/src/routes/table/+page.svelte](/home/jovin/projects/BimAtlas/apps/web/src/routes/table/+page.svelte)

1. **Update formula guide content and suggestion metadata.**

- Add explicit guide entries/examples for:
  - `=ENTITY.Attribute`
  - nested `=ENTITY.PropertySets.PsetWallCommon`
  - `[Display Text](=ENTITY.Attribute)` header syntax and “top headers only” note.
- Ensure formula guide overlay renders these new entries.
- Files:
  - [/home/jovin/projects/BimAtlas/apps/web/src/lib/table/formulas.ts](/home/jovin/projects/BimAtlas/apps/web/src/lib/table/formulas.ts)
  - [/home/jovin/projects/BimAtlas/apps/web/src/routes/table/+page.svelte](/home/jovin/projects/BimAtlas/apps/web/src/routes/table/+page.svelte)

1. **Add/expand tests for new behaviors.**

- Playwright fixture tests:
  - add custom column after defaults.
  - default columns cannot be deleted.
  - `=ENTITY.Attribute` populates all entity rows.
  - nested path formula works.
  - non-existent attribute yields empty/NULL display.
  - `[Display Text](Formula)` updates top header label while retaining formula behavior.
  - formula guide includes new syntax docs.
- Update fixtures with representative nested attribute data.
- Files:
  - [/home/jovin/projects/BimAtlas/apps/web/tests/table-spreadsheet/table-spreadsheet.spec.ts](/home/jovin/projects/BimAtlas/apps/web/tests/table-spreadsheet/table-spreadsheet.spec.ts)
  - [/home/jovin/projects/BimAtlas/apps/web/src/lib/table/fixtures.ts](/home/jovin/projects/BimAtlas/apps/web/src/lib/table/fixtures.ts)

1. **Validation pass.**

- Run frontend checks and spreadsheet suite:
  - `pnpm run check`
  - `pnpm run test:spreadsheet`
- Confirm no regressions in locking/protected behavior and formula-bar interactions.

## Key implementation notes

- Keep existing A1 formula behavior for regular cells; add `ENTITY.` path logic as an additive capability for header-driven/custom-column use.
- Resolve values from row-level entity data (not by re-querying backend per cell).
- Preserve current null-safe rendering conventions (`value == null ? "" : String(value)`).
