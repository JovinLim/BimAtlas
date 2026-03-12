# Filter Logic Tree — UX Wireframes

## 1. Search Modal — Logic Builder

### Layout

- **Header:** Filter set name, color picker.
- **Root group selector:** Toggle or dropdown:
  - "Match ALL of the following:"
  - "Match ANY of the following:"
- **Content area:** Vertical list of items.

### Indentation

- **No nested bounding boxes.** Use subtle left-edge vertical guide lines.
- **Depth 0 (root):** No indent; left edge flush.
- **Depth 1:** Single vertical line (e.g. 4px wide, muted color) on left.
- **Depth 2:** Double vertical line (e.g. 8px total) on left.

### Actions

- **Primary:** `+ Add Filter Set` — adds a leaf at the current depth (or at root if no sub-group).
- **Secondary (⋮ menu):** `Add Sub-group` — adds a nested group. Only visible when depth < 2 (i.e. at root or at depth 1).
- **Per-row:** Edit, Delete, (for groups) Add Sub-group in menu.

### Depth Cap

- At depth 2, only leaf nodes. Sub-group option hidden.
- At depth 1, allow adding subgroup or leaf.

### Terminology

- Replace all `AND`/`OR` labels with:
  - **Match ALL:** "Match ALL of the following:"
  - **Match ANY:** "Match ANY of the following:"

---

## 2. Display Order Panel (Separate)

- **Location:** Flat panel, separate from logic builder.
- **Purpose:** Color priority / display order only. Does not affect logic evaluation.
- **Content:** List of applied filter sets with drag handles.
- **Behavior:** Drag-and-drop to reorder. Higher in list = higher color precedence (or vice versa; pick one and document).
- **Rule text:** "When elements match multiple sets, the topmost set's color wins."

---

## 3. Applied Filter Set Card Summary

- **Current:** Single-line summary of conditions.
- **New:** Tree-aware summary, e.g.:
  - `ALL( class=IfcWall, ANY( Name contains "Core", Tag is "A1" ) )`
- **Entry point:** Edit button opens group-aware editor.

---

## 4. Component Separation

| Component | Responsibility |
|-----------|----------------|
| Logic builder | Edit nested expression tree (max depth 2) |
| Display order panel | Reorder applied sets for color precedence |
| Applied set card | Summary + edit entry point |

---

## 5. Technical Spike Notes

- **Backend:** Recursive tree-to-SQL compiler; reuse existing clause builders.
- **Frontend:** `FilterGroupEditor` recursive component with depth enforcement; keyboard navigation for accessibility.
