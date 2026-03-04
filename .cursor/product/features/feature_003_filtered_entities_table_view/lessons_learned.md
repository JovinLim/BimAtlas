## Hard Constraints

- The database schema and API use UUID string identifiers (`project_id`, `branch_id`, `revision_id`); all new code must treat IDs as strings.
- IFC geometry is stored as BYTEA and must remain opaque; the table feature must not parse or expose geometry in the UI.
- Use the current filtered stream output (`searchState.products`) as the source of truth for the table; do not re-evaluate filter logic in the popup.
- Bottom-sheet templates are persisted per project (sheet_template table); in-session sheet state remains multi-sheet. Template save/load requires projectId.
- Table and lock-rail row/header heights and border width must use the CSS variables defined on `.table-page` (`--table-header-height`, `--table-subheader-height`, `--table-row-height`, `--table-grid-border-width`, `--lock-rail-width`) so EntityGrid and BottomSheet stay aligned; do not hardcode pixel heights in lock-rail or table cell rules.
- Entity attribute data for ENTITY.* columns is fetched on demand: when the user commits a header formula that uses ENTITY paths, the table calls POST `/table/entity-attributes` with the current product globalIds and the required top-level paths; the table does not receive attribute payloads via BroadcastChannel.

## Resolved Pitfalls

- Playwright headed runs can race Svelte hydration for new buttons; a short retry loop around the first click on \"Add row\" made the spreadsheet tests robust without changing the user-facing behavior.
- Sticky grid headers (column letters and row indices) initially used translucent backgrounds, so scrolled rows were visible behind the first row/column; switching those backgrounds to match the table page color fixed the bleed-through while preserving the Excel-like layout.
- Optional Univer loading can break Vite import analysis if `@univerjs/core` is referenced as a static string in `import()`. Using a variable with `/* @vite-ignore */` keeps the integration path optional while avoiding hard module-resolution failures in dev/test.
- `onDestroy` executes during SSR for route render teardown, so direct `window` access there can throw `window is not defined`. Wrapping add/remove keyboard-listener calls with a `typeof window !== "undefined"` guard prevents 500s on `/table` SSR.
- Formula UX that supports click-to-insert refs (typing `=` then clicking another cell) must intercept `mousedown` before focus changes to avoid losing the formula compose context. Handling this at the route level with pointer callbacks keeps both top and bottom grids consistent without duplicating formula state in each component.
- Treating formula evaluation errors as committed `#ERROR` values destroys the user's original expression and makes correction harder. Preserve the typed expression as the committed cell value when evaluation fails, so users can fix formulas in place.
- After Enter commit, only clearing selection state left the cell input focused, so typing still edited the cell. Call `blur()` on the cell input in the Enter key handler (in both EntityGrid and BottomSheet) so focus leaves the input and Enter fully escapes edit mode.
- When the selected cell displays the raw formula, a subsequent blur can fire with the displayed computed value and overwrite the stored formula. In `commitCell`, ignore commits when the cell is not active, has a stored formula, and the incoming value equals the already-committed computed value.
- Bottom-sheet rows are user-added and not IFC entities; column C there must be editable. Only the top entity grid’s IfcClass/Global ID columns are protected; `resolveCellByRef` marks sheet cells as non-protected.
- Lock-rail rows drifted from table rows because rail buttons used a fixed height plus a border, yielding a different effective row height than table cells. Use shared CSS variables and, for rail segments, `calc(var(--table-row-height) + var(--table-grid-border-width))` (with `box-sizing: border-box`) so the rail and table share the same row height and stay aligned when variables change.
- Playwright can click toolbar/header buttons before Svelte hydration wires handlers, which looks like a successful click but leaves state unchanged. Use short retry loops in fixture tests for newly added UI controls (for example Add custom column and Formula guide) and verify the expected post-click element appears before continuing.
- Sending full product attributes via BroadcastChannel (e.g. context-attributes messages) can fail to reach the table or hit size limits. Requesting attributes only when the user applies an ENTITY formula and fetching them from the backend (POST /table/entity-attributes) ensures the table gets the data it needs and keeps the context payload small.
- BottomSheet previously used entries as $bindable for two-way binding. When refactoring to multi-sheet state (derived activeSheet), the parent cannot bind to a derived value. Switching to a controlled pattern (entries prop + onEntriesChange) lets the parent own the state and update the active sheet.
- Persisting sheet rows as domain-shaped objects (`entityGlobalId`, `category`, etc.) locks storage to current UI semantics and makes schema evolution painful. Serializing to a sparse Excel-like `cells` map (`A1` refs with value/formula) plus row metadata keeps payloads compact and lets frontend hydration stay stable while still supporting legacy payload migration on read.

## Univer feasibility (timeboxed spike)

- **Decision:** Defer Univer for v1. Use Svelte-native EntityGrid + BottomSheet.
- **Criteria used:** Bundle size and framework mismatch (Univer brings React/RxJS); popup cold-start and memory with a graphics-heavy main app; adequacy of lightweight grid for lock/unlock, protected columns, and sheet area.
- **Adapter:** `apps/web/src/lib/table/engine.ts` provides `getTableEngine()` and `loadUniverEngine()` so a Univer-based engine can be swapped in later (e.g. via `VITE_TABLE_ENGINE=univer`) if requirements justify it.
