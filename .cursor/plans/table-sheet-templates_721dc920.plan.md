---
name: table-sheet-templates
overview: Extend Feature 003 with project-scoped JSONB sheet templates, multi-sheet support in `/table`, and a bottom-sheet toolbar flow for save/load/search templates (name required).
todos:
  - id: db-sheet-template-schema
    content: Add project-scoped sheet_template table + migration + schema doc update
    status: completed
  - id: api-sheet-template-graphql
    content: Implement db.py helpers and GraphQL types/resolvers for create/list/search sheet templates
    status: completed
  - id: web-client-template-ops
    content: Add template GraphQL operations to web client
    status: completed
  - id: table-multi-sheet-state
    content: Refactor /table route state and snapshot model to multi-sheet + active sheet
    status: completed
  - id: bottom-sheet-toolbar-ux
    content: Extend bottom-sheet toolbar with save/load/search template flow and keep + Add row
    status: completed
  - id: tests-and-feature-artifacts
    content: Add backend/frontend tests and update active_task/lessons learned feature artifacts
    status: completed
isProject: false
---

# Extend Table With Multi-Sheet Templates

## Goal

Implement project-scoped bottom-sheet template persistence and a multi-sheet UX in `/table`, while keeping the existing filtered-entity table behavior and formula interactions intact.

## Confirmed Product Decisions

- Template save/load scope: **active sheet only** (per your selection).
- Keep existing table source-of-truth constraints: top entity grid remains driven by `searchState.products`; no filter re-evaluation.

## Implementation Steps

1. **Database schema: add project-scoped sheet template table**

- Add a new relational table in `[infra/init-age.sql](infra/init-age.sql)`, e.g. `sheet_template`, with:
  - `sheet_template_id UUID PK`
  - `project_id UUID NOT NULL` FK to `project(project_id)` with cascade
  - `name VARCHAR NOT NULL`
  - `sheet JSONB NOT NULL` (active-sheet payload)
  - `created_at TIMESTAMPTZ DEFAULT now()`
  - `updated_at TIMESTAMPTZ DEFAULT now()`
- Add index/constraint strategy:
  - `INDEX(project_id)`
  - `UNIQUE(project_id, name)` (enforces required meaningful naming and avoids duplicates per project)
- Add migration file in `[infra/migrations/](infra/migrations/)` for existing DBs.
- Mirror schema change in test bootstrap SQL inside `[apps/api/tests/conftest.py](apps/api/tests/conftest.py)`.
- Update canonical schema doc in `[.cursor/database/database-schema.md](.cursor/database/database-schema.md)` with the new table + FK relationship section.

1. **Backend persistence API (GraphQL-first, existing repo pattern)**

- Add DB helpers in `[apps/api/src/db.py](apps/api/src/db.py)`:
  - `create_sheet_template(project_id, name, sheet_json)`
  - `fetch_sheet_templates_for_project(project_id)`
  - `search_sheet_templates(query, project_id)`
  - `fetch_sheet_template(sheet_template_id)` (optional but useful for load-by-id)
- Add GraphQL types/inputs in `[apps/api/src/schema/ifc_types.py](apps/api/src/schema/ifc_types.py)` for `SheetTemplate`.
- Add GraphQL queries/mutations in `[apps/api/src/schema/queries.py](apps/api/src/schema/queries.py)`:
  - `sheetTemplates(projectId: String!)`
  - `searchSheetTemplates(query: String!, projectId: String!)`
  - `createSheetTemplate(projectId: String!, name: String!, sheet: JSON/String)`
- Add API tests modeled after filter-set tests:
  - DB-level tests in new test module (e.g. `apps/api/tests/test_sheet_templates.py`)
  - Resolver/API coverage for create/list/search paths.

1. **Client API layer for template CRUD/search**

- Add GraphQL operations in `[apps/web/src/lib/api/client.ts](apps/web/src/lib/api/client.ts)`:
  - `SHEET_TEMPLATES_QUERY`
  - `SEARCH_SHEET_TEMPLATES_QUERY`
  - `CREATE_SHEET_TEMPLATE_MUTATION`
- Keep variable names aligned with existing table route context (`projectId` already exists in table route + protocol).

1. **Refactor `/table` state to support multiple sheets**

- In `[apps/web/src/routes/table/+page.svelte](apps/web/src/routes/table/+page.svelte)`:
  - Replace single-sheet state (`sheetEntries`, `sheetFormulas`, `sheetLockedIds`) with:
    - `sheets: SheetState[]`
    - `activeSheetId: string`
  - Add helpers:
    - create/delete/select sheet
    - resolve active sheet object
    - map cell refs against active sheet rows only
  - Update snapshot/undo/redo to store multi-sheet state (and adjust `[apps/web/src/lib/table/engine.ts](apps/web/src/lib/table/engine.ts)` snapshot type accordingly).
  - Keep top-grid behavior unchanged; only bottom-sheet data model becomes multi-sheet.

1. **Bottom-sheet toolbar + template search UX**

- Extend toolbar in `[apps/web/src/lib/table/BottomSheet.svelte](apps/web/src/lib/table/BottomSheet.svelte)` (it already has `+ Add row`):
  - keep/add `+ Add row` button in toolbar
  - add `Save template` action (opens required-name prompt/input)
  - add template search input (name filter, similar interaction model to IFC/filter searching)
  - add template result list and `Load` action for selected template
- Wire callbacks to parent route so persistence/search calls are handled in `[apps/web/src/routes/table/+page.svelte](apps/web/src/routes/table/+page.svelte)` with current `projectId`.
- Apply loaded template to **active sheet only** (replace active sheet rows/formulas/locks with template payload).

1. **Validation and regression safety**

- Backend:
  - run API tests for new sheet template DB/query/mutation paths.
- Frontend:
  - add/extend spreadsheet tests around:
    - multi-sheet creation/switching
    - save-template requires non-empty name
    - search-by-name filtering
    - load-template hydrates active sheet
    - toolbar add-row remains functional
- Ensure no regressions in existing formula, lock rail, and entity-grid behavior.

1. **Feature tracking artifacts update (per workspace conventions)**

- Append a new in-progress/completed entry in `[.cursor/product/features/feature_003_filtered_entities_table_view/active_task.json](.cursor/product/features/feature_003_filtered_entities_table_view/active_task.json)` referencing this plan.
- Add durable constraints/pitfalls encountered to `[.cursor/product/features/feature_003_filtered_entities_table_view/lessons_learned.md](.cursor/product/features/feature_003_filtered_entities_table_view/lessons_learned.md)`.
- If behavior scope changes materially, update `[.cursor/product/features/feature_003_filtered_entities_table_view/prd.md](.cursor/product/features/feature_003_filtered_entities_table_view/prd.md)` and `[.cursor/product/features/feature_003_filtered_entities_table_view/overview.md](.cursor/product/features/feature_003_filtered_entities_table_view/overview.md)` to reflect persistence + multi-sheet templates.
