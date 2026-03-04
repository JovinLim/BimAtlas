---
feature_id: "FEAT-003"
status: "implemented"
priority: "high"
---

# Feature: Filtered Entities Table View

## 1. Problem Statement

Users need a tabular view of the IFC entities that match the currently applied filter sets, with the ability to lock/unlock rows, enforce read-only identity columns (e.g. IfcClass), and use a lower sheet area for quantity surveying or other spreadsheet-style interactions. The table should open in a popup tab (like the Graph view) and stay in sync with the main window's filtered result set.

## 2. Core Requirements

- **Req 1 (Entry point):** The main page must expose a "Table" button next to Graph/Search/Attributes. Clicking it opens a popup tab that shows the table view. Popup lifecycle and context sync must follow existing popup conventions (URL params, BroadcastChannel handshake).
- **Req 2 (Data source):** The table must display the current filtered entities from `searchState.products` (the actual streamed result set). No re-evaluation of filter logic in the popup; the stream output is the source of truth.
- **Req 3 (Lock model):** Rows may be "locked" or "unlocked". Locked rows are read-only for editable cells; unlocked rows allow edits where permitted.
- **Req 4 (Protected columns):** Certain columns are permanently read-only (e.g. `IfcClass`, Global ID). These must never be editable regardless of lock state.
- **Req 5 (Split layout):** The popup has two segments: top = IFC entity table (filtered rows); bottom = sheet interaction area for user-defined content (e.g. quantity surveying notes, formulas, row references).
- **Req 6 (Testability):** A test harness mode (query flag `?fixture=1`, fixture injection) must allow the table popup to be validated in isolation with dummy data, without live IFC streaming.

## 3. Out of Scope (Strict Constraints)

- No backend persistence of table/sheet state in v1 unless explicitly required later. Session or local storage only for sheet interactions.
- Do not parse or expose BYTEA geometry in the table; geometry remains opaque.
- Do not change the filter application pipeline; table consumes existing `searchState.products` only.

## 4. Success Criteria

- [x] Main page has a Table button that opens the table popup with correct URL and context sync.
- [x] Table popup shows filtered entities in the top segment; data matches `searchState.products` when opened from main window (lean context via BroadcastChannel).
- [x] Lock/unlock toggles per row work; protected columns (e.g. IfcClass, Global ID) are never editable.
- [x] Bottom segment supports sheet-style interactions (e.g. notes, quantity formulas, columns A–F).
- [x] Isolated Playwright tests with dummy data cover spreadsheet behaviors; README documents headless and headed Chromium test scripts.

## 5. Implemented Extensions (Current Behavior)

- **Multi-sheet:** Bottom segment supports multiple sheets (tabs). Add sheet via "+ Sheet"; switch between sheets; each sheet has its own entries, formulas, and lock state. Undo/redo includes multi-sheet state.
- **Sheet templates:** Project-scoped persistence. Save template (name required) stores active sheet as JSONB; search by name; load applies template to active sheet. Template controls visible when projectId is set.
- **Formula bar:** Active cell ref, formula/value input, Undo, Redo, and **View full** button. Formula dropdown (e.g. `=S` → SUM), formula guide overlay. Enter commits and deselects; Escape cancels. Click-to-insert cell refs when composing formulas; drag selection across top grid and bottom sheet.
- **ENTITY formula columns:** User can add custom top columns. Header formulas support `=ENTITY.path` (e.g. `=ENTITY.PropertySets`, `=ENTITY.PropertySets.PsetWallCommon`) with nested JSON traversal and null-safe display. Top-header-only alias syntax: `[Display Text](=ENTITY.path)`. Default columns (Global ID, IFC Class, Name, Description, Object Type, Tag) are undeletable and protected where applicable.
- **On-demand entity attributes:** The table receives only lean product context (no attributes) from the main page. When the user commits a header formula that uses ENTITY paths, the frontend calls **POST /table/entity-attributes** with `branchId`, `revision`, `globalIds`, and requested top-level `paths`. The backend returns `attributesByGlobalId`; the table merges these into products so ENTITY columns resolve. Only requested attribute keys are fetched.
- **View full cell overlay:** Formula bar includes a "View full" button (enabled when a cell is selected). It opens an overlay at 75% width/height of the viewport, vertically scrollable only, showing the full cell contents. If the content is JSON, it is pretty-printed for readability. Close via ×, backdrop click, or Escape.
- **Segment toolbar:** Total entities count, Find selected element, Lock all / Unlock all, Add column, Formula guide. Lock rail is outside the table (left) for both top entity grid and bottom sheet; column layout A–F for data columns.
- **Engine:** Svelte-native EntityGrid and BottomSheet; Univer deferred. `apps/web/src/lib/table/engine.ts` provides an adapter for a future Univer-based engine if needed.

## 6. Key Artifacts

- **Routes:** `apps/web/src/routes/table/+page.svelte` (table popup), main page Table button and `sendTableContext()`.
- **Components:** `EntityGridDynamic.svelte`, `BottomSheet.svelte`; formula bar and overlays in table route.
- **Protocol:** `apps/web/src/lib/table/protocol.ts` (TABLE_CHANNEL, context payload, TableMessage types).
- **Formulas:** `apps/web/src/lib/table/formulas.ts` (evaluateFormula, extractEntityPath, resolveEntityPath, FORMULA_SUGGESTIONS, parseHeaderAliasFormula).
- **API:** POST `/table/entity-attributes` (body: `branchId`, `revision`, `globalIds`, `paths`; response: `attributesByGlobalId`). GraphQL: `sheetTemplates`, `searchSheetTemplates`, `sheetTemplate`, `createSheetTemplate` (project-scoped). DB: `sheet_template` table (project_id, name, sheet JSONB).
- **Tests:** Playwright spreadsheet tests; run with `pnpm run test:spreadsheet` (headless) or `pnpm run test:spreadsheet:headed`.
