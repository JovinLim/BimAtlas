---
feature_id: "FEAT-001"
status: "implemented"
priority: "high"
---

# Feature: Dynamic Filter Sets & Attribute Search

## 1. Problem Statement

Users need the ability to isolate specific IFC entities (e.g., structural columns, specific MEP systems) without loading the entire project. To support reusable workflows, users must be able to create named, configurable "Filter Sets" stored as JSONB, save them to a branch, and dynamically toggle them on/off to compose complex database views.

## 2. Core Requirements

- **Req 1 (CRUD):** The system must provide GraphQL mutations to create, read, update, and delete rows in the `filter_sets` table, capturing the `filters` (JSONB) and intra-set `logic` ('AND'/'OR').
- **Req 2 (State Management):** The system must provide mutations to attach/detach a `filter_set_id` to a `branch_id` in the `branch_applied_filter_sets` table, defining the inter-set `combination_logic`.
- **Req 3 (Query Engine):** The core `searchIfcEntities` GraphQL query must dynamically generate a safe SQL `WHERE` clause by reading all currently applied filter sets for the requested branch, respecting both the intra-set `logic` and the `combination_logic` between sets.
- **Req 4 (JSONB Translation):** The backend must translate the JSON arrays stored in the `filters` column into valid PostgreSQL JSON path operators (e.g., `@>`, `->>`) against the `ifc_entity.attributes` column.
- **Req 5 (Filter Logic Tree):** The system must support nested Match ALL / Match ANY logic trees (max depth 2) stored in `filters` JSONB. Canonical shape: root group with `kind: "group"`, `op: "ALL" | "ANY"`, and `children` (group or leaf nodes). Leaf nodes have `kind: "leaf"` and `mode` (class, attribute, relation). Legacy flat arrays are auto-wrapped for backward compatibility. See `docs/filter-logic-tree-spec.md`.
- **Req 6 (Tree UI):** The Search page must provide a tree-aware editor (FilterTreeEditor) with depth enforcement, add filter/ sub-group actions, and per-group Match ALL/ANY toggle. Applied filter sets display tree-aware summaries; display order panel supports reordering for color precedence.

## 3. Out of Scope (Strict Constraints)

- Do not implement graph traversal or use Apache AGE Cypher queries; this is strictly relational `JSONB` attribute filtering.
- Do not return or parse the `BYTEA` geometry column in the search payload to prevent memory overflow.
- Do not execute raw user-provided SQL strings. All JSONB filter rules must be parsed and parameterized via the ORM/Query Builder to prevent SQL injection.

## 4. Success Criteria

- [x] A `filter_set` containing multiple rules (e.g., `IfcClass = 'IfcWall'` AND `FireRating = '2HR'`) can be saved to the database.
- [x] The filter set can be successfully toggled to "applied" via the `branch_applied_filter_sets` junction table.
- [x] Querying the branch successfully returns only entities that satisfy the composed logic of all applied filter sets.
- [x] Query execution utilizes the `idx_ifc_attributes` GIN index.
- [x] Filter sets can be stored and evaluated as nested trees (Match ALL / Match ANY, max depth 2).
- [x] Legacy flat filter arrays are canonicalized to tree shape on read/write.
