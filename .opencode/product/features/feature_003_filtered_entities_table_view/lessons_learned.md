## Hard Constraints

- The database schema and API use UUID string identifiers (`project_id`, `branch_id`, `revision_id`); all new code must treat IDs as strings.
- IFC geometry is stored as BYTEA and must remain opaque; the table feature must not parse or expose geometry in the UI.
- Use the current filtered stream output (`searchState.products`) as the source of truth for the table; do not re-evaluate filter logic in the popup.
- Table and sheet state in v1 is session/local only unless PRD is updated to require backend persistence.
- Table and lock-rail row/header heights and border width must use the CSS variables defined on `.table-page` (`--table-header-height`, `--table-subheader-height`, `--table-row-height`, `--table-grid-border-width`, `--lock-rail-width`) so EntityGrid and BottomSheet stay aligned; do not hardcode pixel heights in lock-rail or table cell rules.

## Resolved Pitfalls

- Playwright headed runs can race Svelte hydration for new buttons; a short retry loop around the first click on "Add row" made the spreadsheet tests robust without changing the user-facing behavior.
- Sticky grid headers (column letters and row indices) initially used translucent backgrounds, so scrolled rows were visible behind the first row/column; switching those backgrounds to match the table page color fixed the bleed-through while preserving the Excel-like layout.
- Optional Univer loading can break Vite import analysis if `@univerjs/core` is referenced as a static string in `import()`. Using a variable with `/* @vite-ignore */` keeps the integration path optional while avoiding hard module-resolution failures in dev/test.
- `onDestroy` executes during SSR for route render teardown, so direct `window` access there can throw `window is not defined`. Wrapping add/remove keyboard-listener calls with a `typeof window !== "undefined"` guard prevents 500s on `/table` SSR.
- Formula UX that supports click-to-insert refs (typing `=` then clicking another cell) must intercept `mousedown` before focus changes to avoid losing the formula compose context. Handling this at the route level with pointer callbacks keeps both top and bottom grids consistent without duplicating formula state in each component.
- Treating formula evaluation errors as committed `#ERROR` values destroys the user's original expression and makes correction harder. Preserve the typed expression as the committed cell value when evaluation fails, so users can fix formulas in place.
- After Enter commit, only clearing selection state left the cell input focused, so typing still edited the cell. Call `blur()` on the cell input in the Enter key handler (in both EntityGrid and BottomSheet) so focus leaves the input and Enter fully escapes edit mode.
- When the selected cell displays the raw formula, a subsequent blur can fire with the displayed computed value and overwrite the stored formula. In `commitCell`, ignore commits when the cell is not active, has a stored formula, and the incoming value equals the already-committed computed value.
- Bottom-sheet rows are user-added and not IFC entities; column C there must be editable. Only the top entity grid's IfcClass/Global ID columns are protected; `resolveCellByRef` marks sheet cells as non-protected.
- Lock-rail rows drifted from table rows because rail buttons used a fixed height plus a border, yielding a different effective row height than table cells. Use shared CSS variables and, for rail segments, `calc(var(--table-row-height) + var(--table-grid-border-width))` (with `box-sizing: border-box`) so the rail and table share the same row height and stay aligned when variables change.

## Univer feasibility (timeboxed spike)

- **Decision:** Defer Univer for v1. Use Svelte-native EntityGrid + BottomSheet.
- **Criteria used:** Bundle size and framework mismatch (Univer brings React/RxJS); popup cold-start and memory with a graphics-heavy main app; adequacy of lightweight grid for lock/unlock, protected columns, and sheet area.
- **Adapter:** `apps/web/src/lib/table/engine.ts` provides `getTableEngine()` and `loadUniverEngine()` so a Univer-based engine can be swapped in later (e.g. via `VITE_TABLE_ENGINE=univer`) if requirements justify it.
