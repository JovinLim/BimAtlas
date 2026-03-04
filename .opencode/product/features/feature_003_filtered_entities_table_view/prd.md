---
feature_id: "FEAT-003"
status: "draft"
priority: "high"
---

# Feature: Filtered Entities Table View

## 1. Problem Statement

Users need a tabular view of the IFC entities that match the currently applied filter sets, with the ability to lock/unlock rows, enforce read-only identity columns (e.g. IfcClass), and use a lower sheet area for quantity surveying or other spreadsheet-style interactions. The table should open in a popup tab (like the Graph view) and stay in sync with the main window's filtered result set.

## 2. Core Requirements

- **Req 1 (Entry point):** The main page must expose a "Table" button next to Graph/Search/Attributes. Clicking it opens a popup tab that shows the table view. Popup lifecycle and context sync must follow existing popup conventions (URL params, BroadcastChannel handshake).
- **Req 2 (Data source):** The table must display the current filtered entities from `searchState.products` (the actual streamed result set). No re-evaluation of filter logic in the popup; the stream output is the source of truth.
- **Req 3 (Lock model):** Rows may be "locked" or "unlocked". Locked rows are read-only for editable cells; unlocked rows allow edits where permitted.
- **Req 4 (Protected columns):** Certain columns are permanently read-only (e.g. `IfcClass`). These must never be editable regardless of lock state.
- **Req 5 (Split layout):** The popup has two segments: top = IFC entity table (filtered rows); bottom = sheet interaction area for user-defined content (e.g. quantity surveying notes, formulas, row references).
- **Req 6 (Testability):** A test harness mode (query flag, fixture injection, or mocked channel payload) must allow the table popup to be validated in isolation with dummy data, without live IFC streaming.

## 3. Out of Scope (Strict Constraints)

- No backend persistence of table/sheet state in v1 unless explicitly required later. Session or local storage only for sheet interactions.
- Do not parse or expose BYTEA geometry in the table; geometry remains opaque.
- Do not change the filter application pipeline; table consumes existing `searchState.products` only.

## 4. Success Criteria

- [ ] Main page has a Table button that opens the table popup with correct URL and context sync.
- [ ] Table popup shows filtered entities in the top segment; data matches `searchState.products` when opened from main window.
- [ ] Lock/unlock toggles per row work; protected columns (e.g. IfcClass) are never editable.
- [ ] Bottom segment supports sheet-style interactions (e.g. notes, quantity formulas).
- [ ] Isolated Playwright tests with dummy data cover spreadsheet behaviors; README documents headless and headed Chromium test scripts.
