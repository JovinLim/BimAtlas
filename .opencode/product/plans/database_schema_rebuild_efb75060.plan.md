---
name: Database Schema Rebuild
overview: Rebuild the database to match the new schema in database-schema.md (UUID PKs, unified ifc_entity table with JSONB attributes, single geometry BYTEA column), update all API code and tests to work with the new schema, and ensure FEAT-001 Dynamic Filter Sets is fully supported.
todos:
  - id: rebuild-init-sql
    content: Rewrite infra/init-age.sql with full target schema (UUID PKs, ifc_entity, new tables, GIN index, practical additions)
    status: completed
  - id: update-db-py
    content: "Update apps/api/src/db.py: all SQL queries for new table/column names, JSONB attribute extraction, UUID handling, filter engine rewrite for JSONB operators"
    status: completed
  - id: update-geometry-py
    content: "Refactor IfcProductRecord -> IfcEntityRecord in geometry.py: single geometry blob, attributes dict, updated content_hash"
    status: completed
  - id: update-ingestion-py
    content: Update ingestion.py SQL statements and data types for new schema
    status: completed
  - id: update-age-client
    content: Update age_client.py graph properties (ifc_global_id, UUID branch_id, revision_seq for temporal filtering)
    status: completed
  - id: update-graphql-types
    content: Update ifc_types.py and queries.py for UUID IDs and JSONB attribute extraction in resolvers
    status: completed
  - id: update-tests
    content: Update conftest.py SCHEMA_SQL and all 7 test files for new schema
    status: completed
  - id: update-readme
    content: Update README.md to reflect new schema, JSONB attributes, new tables, and updated examples
    status: completed
isProject: false
---

# Database Schema Rebuild Plan

## Gap Analysis: Current vs Target

The existing database ([init-age.sql](infra/init-age.sql)) and the target schema ([database-schema.md](.cursor/database/database-schema.md)) differ significantly:

### Table-Level Changes

| Current                                        | Target                                                              | Change                                                  |
| ---------------------------------------------- | ------------------------------------------------------------------- | ------------------------------------------------------- |
| `projects` (SERIAL PK)                         | `project` (UUID PK)                                                 | Rename + UUID                                           |
| `branches` (SERIAL PK)                         | `branch` (UUID PK)                                                  | Rename + UUID, add `is_active`, add `default_schema_id` |
| `revisions` (SERIAL PK)                        | `revision` (UUID PK)                                                | Rename + UUID, new columns                              |
| `ifc_products` (SERIAL PK, individual columns) | `ifc_entity` (UUID PK, JSONB `attributes`, single `geometry` BYTEA) | **Major restructure**                                   |
| `filter_sets` / `branch_applied_filter_sets`   | Same names, UUID PKs                                                | UUID migration                                          |
| --                                             | `ifc_schema`                                                        | **New table**                                           |
| --                                             | `validation_rule`                                                   | **New table**                                           |
| --                                             | `merge_request`                                                     | **New table**                                           |
| --                                             | `merge_conflict_log`                                                | **New table**                                           |

### Critical `ifc_entity` Column Changes

The most impactful change is the restructuring of `ifc_products` into `ifc_entity`:

- **Individual attribute columns** (`name`, `description`, `object_type`, `tag`, `contained_in`) move into a single `attributes JSONB` column
- **Four geometry columns** (`vertices`, `normals`, `faces`, `matrix`) merge into a single `geometry BYTEA`
- `**global_id` becomes `ifc_global_id`
- `**valid_from_rev` / `valid_to_rev` (integer FKs) become `created_in_revision_id` / `obsoleted_in_revision_id` (UUID FKs)

### Practical Additions (Not in Schema Doc, Required by Codebase)

The schema doc omits several columns the existing codebase requires. These will be added:

- `**content_hash TEXT` on `ifc_entity`: required by the SCD Type 2 diff engine in [ingestion.py](apps/api/src/services/ifc/ingestion.py) (lines 182-219 compute diffs via content hash)
- `**ifc_filename TEXT` on `revision`: required by the ingestion pipeline ([ingestion.py](apps/api/src/services/ifc/ingestion.py) line 234-238 stores the uploaded filename)
- `**description TEXT`** and `**created_at TIMESTAMPTZ\*\`on`project`: used throughout the API ([db.py](apps/api/src/db.py) lines 103-127)
- `**created_at TIMESTAMPTZ` on `branch` and `revision`: used by the API layer
- `**revision_seq SERIAL` on `revision`: the SCD Type 2 temporal query pattern (`valid_from_rev <= X AND valid_to_rev > X`) requires orderable revision identifiers; UUID PKs are not temporally sortable, so a monotonic sequence is needed for efficient temporal queries and AGE graph properties

### UUID Strategy and Temporal Ordering

UUID PKs introduce a complication: the current SCD Type 2 queries rely on integer comparison (`<=`, `>`) for revision ordering. The solution:

- `revision.revision_id` is the UUID PK (matches schema doc)
- `revision.revision_seq SERIAL` provides monotonic ordering per branch
- `ifc_entity` stores `created_in_revision_id` and `obsoleted_in_revision_id` as UUID FKs (schema compliance)
- Temporal SQL queries JOIN or denormalize via `revision_seq` for ordering
- AGE graph properties use `revision_seq` integers (AGE does not support UUID in properties)

### FEAT-001 Alignment

The `attributes JSONB` column on `ifc_entity` is the key enabler for [FEAT-001](apps/../.cursor/product/features/feature_001_dynamic_filter_sets/prd.md) Req 4: "translate JSON arrays stored in filters column into valid PostgreSQL JSON path operators (e.g., `@>`, `->>`) against the `ifc_entity.attributes` column." A **GIN index** on `ifc_entity.attributes` must be created to satisfy success criterion 4.

---

## Phase 1: Rebuild `init-age.sql`

Rewrite [infra/init-age.sql](infra/init-age.sql) to implement the full target schema:

- Enable `uuid-ossp` or use `gen_random_uuid()` for UUID generation
- Create tables in dependency order: `ifc_schema` -> `project` -> `branch` -> `revision` -> `ifc_entity` -> `filter_sets` -> `branch_applied_filter_sets` -> `merge_request` -> `merge_conflict_log` -> `validation_rule`
- Include the practical additions listed above
- Create indexes including `idx_ifc_attributes GIN` on `ifc_entity.attributes`
- Create partial indexes for active entities (`WHERE obsoleted_in_revision_id IS NULL`)
- Set up AGE extension and `bimatlas` graph

---

## Phase 2: Update API Data Layer

### 2a. Update `db.py`

[apps/api/src/db.py](apps/api/src/db.py) contains all SQL queries. Every function needs updating:

- **Project/Branch/Revision helpers** (lines 99-208): table names, column names, UUID handling
- **Product query functions** (lines 215-300): `ifc_products` -> `ifc_entity`, individual column SELECTs -> JSONB extraction (`attributes->>'Name'`, etc.), `global_id` -> `ifc_global_id`
- **Revision diff** (lines 314-372): new table/column names
- **Filter set CRUD** (lines 378-623): UUID PKs instead of SERIAL, column name adjustments
- **Filter engine** (`_build_filter_clause`, lines 631-663): rewrite for JSONB operators -- `name ILIKE %s` becomes `attributes->>'Name' ILIKE %s`, class filter stays as `ifc_class = %s`
- **Delete operations** (lines 458-508): new table names
- Remove debug logging artifact (lines 386-398 in `create_filter_set`)

### 2b. Update `geometry.py`

[apps/api/src/services/ifc/geometry.py](apps/api/src/services/ifc/geometry.py):

- Rename `IfcProductRecord` -> `IfcEntityRecord`
- Replace individual geometry fields (`vertices`, `normals`, `faces`, `matrix`) with a single serialized `geometry: bytes | None`
- Replace individual attribute fields (`name`, `description`, `object_type`, `tag`, `contained_in`) with `attributes: dict` (serialized as JSONB)
- Keep `ifc_class` and `ifc_global_id` as separate fields (they remain columns)
- Update `_compute_content_hash` to hash the JSONB attributes dict and geometry blob
- Define a serialization format for the geometry blob (e.g., msgpack or a simple header+buffers format)

### 2c. Update `ingestion.py`

[apps/api/src/services/ifc/ingestion.py](apps/api/src/services/ifc/ingestion.py):

- Update `_create_revision` SQL (new column names)
- Update `_load_current_hashes` SQL (`ifc_products` -> `ifc_entity`, `global_id` -> `ifc_global_id`)
- Update `_close_product_rows` SQL
- Update `_insert_product_rows` SQL: individual columns -> `attributes` JSONB + single `geometry` BYTEA
- Update data type references (`IfcProductRecord` -> `IfcEntityRecord`)

### 2d. Update `age_client.py`

[apps/api/src/services/graph/age_client.py](apps/api/src/services/graph/age_client.py):

- Graph node properties: `global_id` -> `ifc_global_id`
- `_rev_filter`: use `revision_seq` integers for temporal comparison (unchanged logic, just field name)
- `branch_id` in graph properties: store as UUID string, adjust matching
- Update `create_node`, `close_node`, `create_edge`, `close_edges_for_node` for property name changes

### 2e. Update `ifc_types.py`

[apps/api/src/schema/ifc_types.py](apps/api/src/schema/ifc_types.py):

- `Branch.id: int` -> `Branch.id: str` (UUID as string in GraphQL)
- `Project.id: int` -> `Project.id: str`
- `Revision.id: int` -> `Revision.id: str`
- `FilterSet.id: int` -> `FilterSet.id: str`
- All `branch_id: int` -> `branch_id: str`

### 2f. Update `queries.py` (GraphQL resolvers)

[apps/api/src/schema/queries.py](apps/api/src/schema/queries.py):

- Change all `branch_id: int` parameters to `branch_id: str` (UUID)
- Change all `project_id: int` parameters to `project_id: str`
- Update row-to-type mapping for JSONB attributes extraction
- Update `row_to_stream_product` for new column structure
- Update `_row_to_product` to extract name/description/etc. from `attributes` JSONB

---

## Phase 3: Update Tests

### 3a. Update `conftest.py`

[apps/api/tests/conftest.py](apps/api/tests/conftest.py):

- Rewrite `SCHEMA_SQL` (lines 87-171) to match the new schema from Phase 1
- Update all fixtures that insert test data (`test_branch`, etc.) for UUID handling

### 3b. Update all 7 test files

Update table/column references and ID types in:

- `test_db.py`, `test_filter_sets.py`, `test_api.py`, `test_ingestion.py`, `test_delete_operations.py`, `test_geometry.py`, `test_setup.py`

---

## Phase 4: Update README

[README.md](README.md):

- Update "Hybrid Storage" section: `ifc_products` -> `ifc_entity`, mention JSONB attributes
- Update "Monorepo Structure" comments
- Update GraphQL example queries if parameter types change (UUID strings vs integers)
- Update "Design Decisions" table to reflect JSONB attribute payload
- Add note about new tables (ifc_schema, validation_rule, merge_request, merge_conflict_log)
- Update "Versioning (SCD Type 2)" section for new column names

---

## Key Risks

- **AGE UUID handling**: AGE agtype properties support strings but not native UUIDs. Branch IDs in graph properties will be stored as string representations.
- **Geometry serialization format**: Need to define and document how `vertices`, `normals`, `faces`, `matrix` are packed into a single `geometry BYTEA`. Recommend msgpack with a defined schema.
- **Test coverage**: With 85+ tests and every SQL query changing, thorough test validation is essential.
