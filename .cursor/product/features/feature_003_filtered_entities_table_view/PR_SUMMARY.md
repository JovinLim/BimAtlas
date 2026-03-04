# PR Summary: Feature 003 — Filtered Entities Table View

## Overview

Adds a popup table view of currently filtered IFC entities, opened from the main page via a **Table** button. The table displays the main window’s `searchState.products` (lean context over BroadcastChannel) in a split layout: a top entity grid with lock/unlock controls and protected columns, and a bottom multi-sheet area for quantity surveying (tabs, rows, columns A–F). Includes formula bar, ENTITY formula columns, sheet templates (project-scoped save/load), and full CSV export.

---

## What Was Implemented

### Core Table Popup
- **Entry point:** Table button on main page opens popup tab with URL params (`projectId`, `branchId`, `revisionId`) and BroadcastChannel context sync
- **Data source:** `searchState.products` as source of truth; no filter re-evaluation in popup
- **Split layout:** Top segment = IFC entity grid; bottom segment = sheet interaction area

### Entity Grid (Top Segment)
- Default columns: Global ID, IFC Class, Name, Description, Object Type, Tag (undeletable, protected where applicable)
- User-added custom columns driven by **ENTITY** formulas (e.g. `=ENTITY.PropertySets`, `=ENTITY.PropertySets.PsetWallCommon`)
- Header alias syntax: `[Display Text](=ENTITY.path)`
- On-demand entity attributes: **POST /table/entity-attributes** when user commits an ENTITY formula; backend returns `attributesByGlobalId`; table merges into products
- Lock/unlock per row; protected columns (IfcClass, Global ID) always read-only
- Lock rail outside table (left); shared CSS variables for row/header alignment

### Bottom Sheet (Multi-Sheet)
- Multiple sheets (tabs); add via "+ Sheet"; each sheet has its own entries, formulas, lock state
- Columns A–F; lock rail; continuous row numbering
- **Sheet templates:** Project-scoped persistence; save (name required), search by name, load applies to active sheet
- Sparse Excel-like `cells` map serialization (v2 JSONB); legacy payload migration on read

### Formula Bar & UX
- Active cell ref, formula/value input, Undo, Redo, **View full** (overlay with full cell contents, JSON pretty-printed)
- Formula dropdown (e.g. `=S` → SUM), formula guide overlay
- Enter commits and deselects; Escape cancels
- Click-to-insert cell refs when composing formulas; drag selection across top grid and bottom sheet
- Invalid formula commits preserve user expression (no `#ERROR` overwrite)
- Undo/redo includes multi-sheet state

### Export & Toolbar
- **Export CSV** in top segment toolbar; merged output (entity columns + sheet columns); UTF-8 BOM; filename `filtered-entities-<revisionId>-<yyyyMMdd-HHmm>.csv`
- Segment toolbar: Total entities, Find selected element, Lock all / Unlock all, Add column, Formula guide

### Engine & Univer Decision
- Svelte-native `EntityGrid` + `BottomSheet`; Univer deferred for v1
- `apps/web/src/lib/table/engine.ts` provides `getTableEngine()` and `loadUniverEngine()` for future swap-in

### Testability
- Fixture mode: `?fixture=1` for deterministic dummy data (no live IFC streaming)
- Playwright tests: `pnpm run test:spreadsheet` (headless), `pnpm run test:spreadsheet:headed`

---

## Key Artifacts

| Area | Path |
|------|------|
| Route | `apps/web/src/routes/table/+page.svelte` |
| Components | `EntityGridDynamic.svelte`, `BottomSheet.svelte` |
| Protocol | `apps/web/src/lib/table/protocol.ts` |
| Formulas | `apps/web/src/lib/table/formulas.ts` |
| CSV | `apps/web/src/lib/table/csv.ts` |
| Engine | `apps/web/src/lib/table/engine.ts` |
| Fixtures | `apps/web/src/lib/table/fixtures.ts` |
| API | POST `/table/entity-attributes`; GraphQL: `sheetTemplates`, `searchSheetTemplates`, `createSheetTemplate` |
| DB | `sheet_template` table (project_id, name, sheet JSONB) |
| Tests | `apps/web/tests/table-spreadsheet/` |

---

## Lessons Learned

### Hard Constraints
- UUID identifiers are strings across API/UI state
- IFC geometry (BYTEA) remains opaque; table must not parse or expose it
- Use `searchState.products` as source of truth; no filter re-evaluation in popup
- Bottom-sheet templates persisted per project; template save/load requires `projectId`
- Table/lock-rail heights use CSS variables on `.table-page`; do not hardcode pixel heights
- Entity attributes for ENTITY.* columns fetched on demand via POST `/table/entity-attributes`; not via BroadcastChannel

### Resolved Pitfalls
- **Playwright hydration:** Short retry loops for first click on new buttons (e.g. Add row, Add column, Formula guide) to avoid pre-hydration clicks
- **Sticky headers:** Translucent backgrounds caused bleed-through; switched to solid table-page color
- **Univer/Vite:** `import()` with variable + `/* @vite-ignore */` keeps optional Univer path without breaking module resolution
- **SSR:** `onDestroy` can run during SSR; guard `window` access with `typeof window !== "undefined"`
- **Formula click-to-insert:** Intercept `mousedown` before focus changes to preserve formula compose context
- **Invalid formulas:** Preserve typed expression on eval failure instead of committing `#ERROR`
- **Enter commit:** Call `blur()` on cell input so Enter fully escapes edit mode
- **Stale blur:** Ignore commits when cell has stored formula and incoming value equals committed computed value
- **Bottom-sheet editability:** Column C and all sheet cells editable; only top-entity IfcClass/Global ID protected
- **Lock-rail alignment:** Use `calc(var(--table-row-height) + var(--table-grid-border-width))` for rail segments
- **BroadcastChannel size:** Request attributes via backend when ENTITY formula applied; avoid full product attributes over channel
- **Multi-sheet binding:** Use controlled pattern (entries prop + onEntriesChange) when parent owns state
- **Template payload:** Sparse `cells` map (A1 refs) instead of domain-shaped objects for schema evolution
- **CSV export:** Use `getTopFallback(ref, product)` when `getCommittedValue` empty; match frontend column set

---

## Current State

- **Status:** Implemented
- **PRD:** All success criteria met; §5 Implemented Extensions documents formula bar, ENTITY columns, View full, sheet templates
- **Plans completed:** filtered-entities-table-view, table-spreadsheet-utilities, entity-formula-columns, table-sheet-templates, export-full-csv
- **Tests:** Playwright spreadsheet suite; headless and headed Chromium scripts documented in README
- **Template controls:** Hidden when `projectId` is null (fixture mode)
