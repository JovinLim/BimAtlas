---
feature_id: "FEAT-001"
status: "draft"
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

## 3. Out of Scope (Strict Constraints)

- Do not implement graph traversal or use Apache AGE Cypher queries; this is strictly relational `JSONB` attribute filtering.
- Do not return or parse the `BYTEA` geometry column in the search payload to prevent memory overflow.
- Do not execute raw user-provided SQL strings. All JSONB filter rules must be parsed and parameterized via the ORM/Query Builder to prevent SQL injection.

## 4. Success Criteria

- [ ] A `filter_set` containing multiple rules (e.g., `IfcClass = 'IfcWall'` AND `FireRating = '2HR'`) can be saved to the database.
- [ ] The filter set can be successfully toggled to "applied" via the `branch_applied_filter_sets` junction table.
- [ ] Querying the branch successfully returns only entities that satisfy the composed logic of all applied filter sets.
- [ ] Query execution utilizes the `idx_ifc_attributes` GIN index.
