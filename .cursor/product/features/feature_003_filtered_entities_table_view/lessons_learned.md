## Hard Constraints

- The database schema and API use UUID string identifiers (`project_id`, `branch_id`, `revision_id`); all new code must treat IDs as strings.
- IFC geometry is stored as BYTEA and must remain opaque; the table feature must not parse or expose geometry in the UI.
- Use the current filtered stream output (`searchState.products`) as the source of truth for the table; do not re-evaluate filter logic in the popup.
- Table and sheet state in v1 is session/local only unless PRD is updated to require backend persistence.

## Resolved Pitfalls

- Playwright headed runs can race Svelte hydration for new buttons; a short retry loop around the first click on \"Add row\" made the spreadsheet tests robust without changing the user-facing behavior.
- Sticky grid headers (column letters and row indices) initially used translucent backgrounds, so scrolled rows were visible behind the first row/column; switching those backgrounds to match the table page color fixed the bleed-through while preserving the Excel-like layout.

## Univer feasibility (timeboxed spike)

- **Decision:** Defer Univer for v1. Use Svelte-native EntityGrid + BottomSheet.
- **Criteria used:** Bundle size and framework mismatch (Univer brings React/RxJS); popup cold-start and memory with a graphics-heavy main app; adequacy of lightweight grid for lock/unlock, protected columns, and sheet area.
- **Adapter:** `apps/web/src/lib/table/engine.ts` provides `getTableEngine()` and `loadUniverEngine()` so a Univer-based engine can be swapped in later (e.g. via `VITE_TABLE_ENGINE=univer`) if requirements justify it.
