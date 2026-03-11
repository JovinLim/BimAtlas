---
name: Validation Schema Management & Subgraph Validation Engine
overview: >
  Implement an integrated IFC validation framework where validation rules and grouping schemas
  are first-class graph citizens (IfcEntity). Includes subgraph-aware validation engine,
  GraphQL CRUD, MCP tool stubs, and a Svelte Schema Browser UI.
todos:
  - id: step-1-database-migration
    content: "Create DB migration to add AGE edge label IfcRelValidationToSchema and ensure IfcValidation/IfcValidationSchema/IfcValidationResult vertex labels exist."
    status: pending
  - id: step-2-validation-entity-crud
    content: "Add db.py functions for CRUD on IfcValidation, IfcValidationSchema, and IfcValidationResult entities using the ifc_entity table."
    status: pending
  - id: step-3-graph-edge-operations
    content: "Extend age_client.py with functions to create/delete IfcRelValidationToSchema edges and query rules linked to a schema."
    status: pending
  - id: step-4-cypher-subgraph-queries
    content: "Add Cypher query templates for subgraph validation traversals (spatial containment, aggregation, connectivity scoping)."
    status: pending
  - id: step-5-validation-engine
    content: "Implement the validation engine service that evaluates rules against a branch/revision, including attribute checks, inheritance checks, and subgraph-scoped validation."
    status: pending
  - id: step-6-graphql-types-mutations
    content: "Define Strawberry GraphQL types, queries, and mutations for validation schemas, rules, linking, and validation runs."
    status: pending
  - id: step-7-mcp-tool-stubs
    content: "Define MCP tool interface stubs for create_subgraph_rule, query_spatial_context, run_validation, list_validation_schemas."
    status: pending
  - id: step-8-frontend-schema-browser
    content: "Build the Svelte Schema Browser popup with SchemaList, SchemaDetail, RuleEditor, and ValidationRunner components."
    status: pending
  - id: step-9-frontend-state-integration
    content: "Wire Schema Browser to GraphQL API, add BroadcastChannel sync, and integrate entry point button on main dashboard."
    status: pending
  - id: step-10-backend-tests
    content: "Write comprehensive pytest tests for entity CRUD, graph edge operations, validation engine, and GraphQL resolvers."
    status: pending
  - id: step-11-verification
    content: "Run full test suite, linting, and manual verification of Schema Browser UI."
    status: pending
isProject: false
---

# Validation Schema Management & Subgraph Validation Engine — Implementation Plan

## References

- **PRD:** `.cursor/product/features/feature_005_validation_schema_management/prd.md`
- **Product Overview:** `.cursor/product/overview.md`
- **Existing validation code:** `apps/api/src/schema/ifc_schema_loader.py`, `apps/api/src/db.py` (fetch/insert_validation_rules)
- **Graph client:** `apps/api/src/services/graph/age_client.py`, `apps/api/src/services/graph/queries.py`
- **GraphQL schema:** `apps/api/src/schema/queries.py`, `apps/api/src/schema/ifc_types.py`
- **Frontend state:** `apps/web/src/lib/state/selection.svelte.ts`, `apps/web/src/lib/state/search.svelte.ts`

## Constraints from Lessons Learned

- All IDs are UUID strings; all entity data flows through the unified `ifc_entity` table with `attributes JSONB`.
- AGE graph nodes use `ifc_global_id` (not `global_id`), `branch_id` as UUID string, and `valid_from_rev`/`valid_to_rev` as `revision_seq` integers (-1 = current).
- Do not modify the existing `validation_rule` table (used for IFC schema metadata).
- All Cypher queries must use the `_validate_id`/`_validate_label`/`_escape_cypher_string` sanitization pattern from `age_client.py`.
- JSONB attribute queries must use parameterized SQL (no raw user SQL).
- Frontend uses Svelte 5 Runes (`$state`, `$derived`, `$effect`) and BroadcastChannel for cross-window sync.

---

## Step 1: Database Migration — AGE Labels & Indexes

**File:** `apps/api/migrations/006_validation_entity_labels.sql`

### Tasks
- [ ] Create AGE vertex labels: `IfcValidation`, `IfcValidationSchema`, `IfcValidationResult` (idempotent, using `SELECT create_vlabel()` pattern from `age_client._ensure_vlabel`).
- [ ] Create AGE edge label: `IfcRelValidationToSchema`.
- [ ] Add a partial index on `ifc_entity` for fast validation entity lookups:
  ```sql
  CREATE INDEX idx_ifc_entity_validation_class
    ON ifc_entity (branch_id, ifc_class)
    WHERE ifc_class IN ('IfcValidation', 'IfcValidationSchema', 'IfcValidationResult')
      AND obsoleted_in_revision_id IS NULL;
  ```

### Constraint
- Migration must be idempotent (use `IF NOT EXISTS` / check-before-create patterns).
- AGE label creation requires LOAD 'age' and search_path setup. Since migrations run as raw SQL against the DB, wrap label creation in a PL/pgSQL block that checks `ag_catalog.ag_label` first.

---

## Step 2: Validation Entity CRUD in `db.py`

**File:** `apps/api/src/db.py` (append new functions)

### Tasks
- [ ] `create_validation_entity(branch_id, revision_id, ifc_class, attributes) -> dict`: Insert an `IfcValidation`, `IfcValidationSchema`, or `IfcValidationResult` row into `ifc_entity`. Generate a UUID for `ifc_global_id`. Compute `content_hash` from attributes. Return the created entity dict.
- [ ] `update_validation_entity(branch_id, global_id, revision_id, new_attributes) -> dict | None`: SCD Type 2 update — close existing row (set `obsoleted_in_revision_id`), insert new row with updated attributes. Return new entity or None if not found.
- [ ] `delete_validation_entity(branch_id, global_id, revision_id) -> bool`: SCD Type 2 delete — close existing row. Return True if found.
- [ ] `fetch_validation_entities(branch_id, ifc_class, revision_seq?) -> list[dict]`: Fetch all current (or at-revision) entities of the specified class. Return list of dicts with `entity_id`, `ifc_global_id`, `ifc_class`, `attributes`.
- [ ] `fetch_validation_entity(branch_id, global_id, revision_seq?) -> dict | None`: Fetch a single entity by global_id.
- [ ] `create_validation_revision(branch_id, commit_message) -> dict`: Create a new revision row for validation changes (no IFC file, author = "system"). Return `{revision_id, revision_seq}`.

### Constraint
- Reuse the existing connection pool (`get_cursor`, `get_conn`/`put_conn`).
- `content_hash` must be SHA-256 of the JSON-serialized attributes (sorted keys) — match existing pattern.
- All queries must be parameterized.

---

## Step 3: Graph Edge Operations for Validation

**File:** `apps/api/src/services/graph/age_client.py` (extend)

### Tasks
- [ ] `create_validation_node(ifc_class, global_id, name, rev_id, branch_id)`: Wrapper around existing `create_node()` that ensures the correct vlabel exists. Identical signature to `create_node` but validates that `ifc_class` is one of the three validation types.
- [ ] `link_rule_to_schema(rule_global_id, schema_global_id, rev_id, branch_id)`: Create an `IfcRelValidationToSchema` edge from the rule node to the schema node.
- [ ] `unlink_rule_from_schema(rule_global_id, schema_global_id, rev_id, branch_id)`: Close the edge (set `valid_to_rev`).
- [ ] `get_rules_for_schema(schema_global_id, rev, branch_id) -> list[str]`: Cypher query to return all `IfcValidation` global_ids linked to a schema at a given revision.
- [ ] `get_schema_for_rule(rule_global_id, rev, branch_id) -> str | None`: Return the schema global_id a rule belongs to.

**File:** `apps/api/src/services/graph/queries.py` (extend)

### Tasks
- [ ] Add Cypher templates:
  - `RULES_FOR_SCHEMA`: Match `(schema {ifc_global_id: ...})<-[r:IfcRelValidationToSchema]-(rule)` with revision filters.
  - `SCHEMA_FOR_RULE`: Match `(rule {ifc_global_id: ...})-[r:IfcRelValidationToSchema]->(schema)` with revision filters.

---

## Step 4: Cypher Subgraph Validation Queries

**File:** `apps/api/src/services/graph/queries.py` (extend)

### Tasks
- [ ] `ENTITIES_IN_SPATIAL_SCOPE`: Given a spatial container (IfcSpace/IfcBuildingStorey) name/global_id and a target class, return all entities connected via `IfcRelContainedInSpatialStructure`:
  ```
  MATCH (spatial {name: '{scope_name}', branch_id: '{bid}'})<-[r:IfcRelContainedInSpatialStructure]-(elem)
  WHERE {spatial_filter} AND {r_filter} AND {elem_filter} AND label(elem) IN [{target_classes}]
  RETURN elem.ifc_global_id AS gid
  ```
- [ ] `ENTITIES_IN_AGGREGATE_SCOPE`: Traverse `IfcRelAggregates` for decomposition scoping.
- [ ] `ENTITIES_CONNECTED_VIA`: Generic traversal for `IfcRelConnectsElements`, `IfcRelVoidsElement`, `IfcRelFillsElement`, `IfcRelDefinesByType`.
- [ ] `ENTITIES_BY_TYPE_DEFINITION`: Elements connected to a specific type object via `IfcRelDefinesByType`.

**File:** `apps/api/src/services/graph/age_client.py` (extend)

### Tasks
- [ ] `get_entities_in_spatial_scope(scope_class, scope_name, target_classes, rev, branch_id) -> list[str]`: Execute the spatial scope Cypher, return global_ids.
- [ ] `get_entities_in_aggregate_scope(parent_global_id, target_classes, rev, branch_id) -> list[str]`: Execute aggregate scope Cypher.
- [ ] `get_entities_connected_via(source_global_id, rel_type, target_classes, rev, branch_id) -> list[str]`: Generic relationship traversal.

### Constraint
- All user-supplied values must pass through `_validate_id`, `_validate_label`, or `_escape_cypher_string`.
- Target class lists must be validated label-by-label.
- Revision scoping must use the existing `_rev_filter` helper.

---

## Step 5: Validation Engine Service

**File:** `apps/api/src/services/validation/engine.py` (new)

### Tasks
- [ ] Define `ValidationResult` dataclass:
  ```python
  @dataclass
  class RuleResult:
      rule_global_id: str
      rule_name: str
      severity: str  # Error, Warning, Info
      passed: bool
      violations: list[dict]  # [{global_id, ifc_class, message}, ...]
  
  @dataclass
  class ValidationRunResult:
      schema_global_id: str
      schema_name: str
      branch_id: str
      revision_seq: int
      results: list[RuleResult]
      summary: dict  # {errors: int, warnings: int, info: int, passed: int}
  ```
- [ ] `evaluate_rule(rule_attrs: dict, branch_id: str, rev: int) -> RuleResult`: Core rule evaluator.
  1. Resolve `TargetClass` with optional inheritance expansion (via `ifc_schema_loader.get_descendants`).
  2. If `SpatialContext` is present, use graph traversal to narrow target entities.
  3. Fetch matching entities from `ifc_entity` (by class + branch + revision).
  4. Apply `Conditions` (attribute checks) to each entity's attributes JSONB.
  5. Collect violations (entities that fail the check).
- [ ] `run_validation(schema_global_id: str, branch_id: str, revision_seq: int | None = None) -> ValidationRunResult`: Orchestrate a full validation run.
  1. Fetch the schema entity.
  2. Get all linked rule global_ids via `get_rules_for_schema`.
  3. Fetch each rule entity's attributes.
  4. Evaluate each rule.
  5. Aggregate results.
  6. Optionally persist result as `IfcValidationResult` entity.

### Attribute Check Operators
- [ ] Implement operator functions:
  - `equals(actual, expected)` — exact match (string/number).
  - `not_equals(actual, expected)` — inverse.
  - `contains(actual, expected)` — substring or list membership.
  - `exists(actual)` — key exists and value is not None/empty.
  - `not_exists(actual)` — inverse.
  - `greater_than(actual, expected)` — numeric comparison.
  - `less_than(actual, expected)` — numeric comparison.
  - `matches(actual, pattern)` — regex match.
- [ ] `resolve_nested_value(attributes: dict, path: str) -> Any`: Walk dotted path (e.g., `PropertySets.Pset_WallCommon.FireRating`) into nested JSONB.

### Constraint
- Do not execute raw SQL from rule definitions; attribute checks run in Python after fetching entities.
- Subgraph scoping uses existing age_client functions.
- Rule evaluation must not load geometry data (exclude `geometry` column in fetch).

---

## Step 6: GraphQL Types, Queries, and Mutations

**File:** `apps/api/src/schema/ifc_types.py` (extend)

### Tasks
- [ ] Define Strawberry types:
  ```python
  @strawberry.type
  class IfcValidationCondition:
      path: str
      operator: str
      value: Optional[str] = None

  @strawberry.type
  class IfcValidationSpatialContext:
      traversal: str
      scope_class: str
      scope_name: Optional[str] = None
      scope_global_id: Optional[str] = None

  @strawberry.type
  class IfcValidationRule:
      global_id: str
      name: str
      description: Optional[str]
      rule_type: str
      target_class: str
      severity: str
      conditions: list[IfcValidationCondition]
      spatial_context: Optional[IfcValidationSpatialContext]
      include_subtypes: bool

  @strawberry.type
  class IfcValidationSchemaType:
      global_id: str
      name: str
      description: Optional[str]
      version: Optional[str]
      is_active: bool
      rules: list[IfcValidationRule]

  @strawberry.type
  class ValidationViolation:
      global_id: str
      ifc_class: str
      message: str

  @strawberry.type
  class ValidationRuleResult:
      rule_global_id: str
      rule_name: str
      severity: str
      passed: bool
      violations: list[ValidationViolation]

  @strawberry.type
  class ValidationRunResultType:
      schema_global_id: str
      schema_name: str
      branch_id: str
      revision_seq: int
      results: list[ValidationRuleResult]
      error_count: int
      warning_count: int
      info_count: int
      passed_count: int
  ```
- [ ] Define input types for rule/schema creation.

**File:** `apps/api/src/schema/queries.py` (extend Query and Mutation)

### Tasks
- [ ] Add queries:
  - `validation_schemas(branch_id: str, revision: Optional[int]) -> list[IfcValidationSchemaType]`
  - `validation_schema(branch_id: str, global_id: str, revision: Optional[int]) -> Optional[IfcValidationSchemaType]`
  - `validation_rules(branch_id: str, schema_global_id: Optional[str], revision: Optional[int]) -> list[IfcValidationRule]`
  - `validation_results(branch_id: str, revision: Optional[int]) -> list[ValidationRunResultType]`
- [ ] Add mutations:
  - `create_validation_schema(branch_id: str, name: str, description: Optional[str], version: Optional[str]) -> IfcValidationSchemaType`
  - `update_validation_schema(branch_id: str, global_id: str, name: Optional[str], description: Optional[str]) -> Optional[IfcValidationSchemaType]`
  - `delete_validation_schema(branch_id: str, global_id: str) -> bool`
  - `create_validation_rule(branch_id: str, name: str, ...) -> IfcValidationRule`
  - `update_validation_rule(branch_id: str, global_id: str, ...) -> Optional[IfcValidationRule]`
  - `delete_validation_rule(branch_id: str, global_id: str) -> bool`
  - `link_rule_to_schema(branch_id: str, rule_global_id: str, schema_global_id: str) -> bool`
  - `unlink_rule_from_schema(branch_id: str, rule_global_id: str, schema_global_id: str) -> bool`
  - `run_validation(branch_id: str, schema_global_id: str, revision: Optional[int]) -> ValidationRunResultType`

### Constraint
- Mutations that create/update entities must auto-create a revision (`create_validation_revision`).
- Batch operations within a single revision where possible (e.g., creating a schema + linking rules).

---

## Step 7: MCP Tool Interface Stubs

**File:** `apps/api/src/services/mcp/tools.py` (new)

### Tasks
- [ ] Define tool interface stubs as Python functions with docstrings and type hints:
  ```python
  def create_subgraph_rule(
      branch_id: str,
      name: str,
      target_class: str,
      conditions: list[dict],
      spatial_context: dict | None = None,
      severity: str = "Error",
  ) -> dict:
      """MCP tool: Create a validation rule with optional subgraph scope.
      
      To be exposed via the MCP server for LlamaIndex agent usage.
      """
      ...

  def query_spatial_context(
      branch_id: str,
      scope_class: str,
      scope_name: str,
      target_class: str | None = None,
      revision: int | None = None,
  ) -> list[dict]:
      """MCP tool: Query entities within a spatial context for validation preview."""
      ...

  def run_validation(
      branch_id: str,
      schema_global_id: str,
      revision: int | None = None,
  ) -> dict:
      """MCP tool: Execute a validation schema against a branch."""
      ...

  def list_validation_schemas(
      branch_id: str,
      revision: int | None = None,
  ) -> list[dict]:
      """MCP tool: List all validation schemas on a branch."""
      ...
  ```
- [ ] Each stub should import and delegate to the actual service functions defined in Steps 2-5.
- [ ] Add `__init__.py` to `apps/api/src/services/mcp/`.

### Constraint
- Do not implement a full MCP server in this phase. Just define the tool functions with proper signatures and docstrings so they can be registered later.
- Tool functions must return JSON-serializable dicts.

---

## Step 8: Frontend — Schema Browser Components

**File:** `apps/web/src/routes/schema/+page.svelte` (new)
**File:** `apps/web/src/routes/schema/+layout.svelte` (new)

### Tasks
- [ ] Create the Schema Browser popup page (follows `/graph`, `/search`, `/table` pattern).
- [ ] Layout: Full-width popup with header, two-panel layout (left: schema list, right: detail/editor).

**File:** `apps/web/src/lib/ui/SchemaList.svelte` (new)

### Tasks
- [ ] Fetch and display all `IfcValidationSchema` entities for the active branch.
- [ ] Each item shows: name, description, rule count, active status.
- [ ] Click handler to select a schema and show its detail view.
- [ ] "New Schema" button at the top.

**File:** `apps/web/src/lib/ui/SchemaDetail.svelte` (new)

### Tasks
- [ ] Display the selected schema's metadata (name, description, version).
- [ ] List all linked `IfcValidation` rules with: name, target class, severity badge, condition summary.
- [ ] Edit/delete buttons per rule.
- [ ] "Add Rule" button to open the RuleEditor.
- [ ] "Run Validation" button to trigger a validation run.

**File:** `apps/web/src/lib/ui/RuleEditor.svelte` (new)

### Tasks
- [ ] Form-based rule editor:
  - Target class selector (dropdown using product class tree from API).
  - "Include subtypes" checkbox.
  - Severity selector (Error/Warning/Info).
  - Condition builder: add/remove condition rows with path input, operator selector, value input.
  - Spatial context section (optional): traversal type selector, scope class input, scope name/global_id input.
- [ ] Save button calls `createValidationRule` or `updateValidationRule` mutation.

**File:** `apps/web/src/lib/ui/ValidationRunner.svelte` (new)

### Tasks
- [ ] Branch/revision selector (reuse existing selectors).
- [ ] "Apply Schema" button triggers `runValidation` mutation.
- [ ] Results display: summary bar (error/warning/info counts), expandable per-rule results showing violation details.

---

## Step 9: Frontend — State & API Integration

**File:** `apps/web/src/lib/api/client.ts` (extend)

### Tasks
- [ ] Add GraphQL queries:
  - `VALIDATION_SCHEMAS_QUERY` — fetch all schemas for a branch.
  - `VALIDATION_SCHEMA_QUERY` — fetch single schema with linked rules.
  - `VALIDATION_RULES_QUERY` — fetch rules for a schema.
  - `VALIDATION_RESULTS_QUERY` — fetch validation run results.
- [ ] Add GraphQL mutations:
  - `CREATE_VALIDATION_SCHEMA_MUTATION`
  - `UPDATE_VALIDATION_SCHEMA_MUTATION`
  - `DELETE_VALIDATION_SCHEMA_MUTATION`
  - `CREATE_VALIDATION_RULE_MUTATION`
  - `UPDATE_VALIDATION_RULE_MUTATION`
  - `DELETE_VALIDATION_RULE_MUTATION`
  - `LINK_RULE_TO_SCHEMA_MUTATION`
  - `UNLINK_RULE_FROM_SCHEMA_MUTATION`
  - `RUN_VALIDATION_MUTATION`

**File:** `apps/web/src/lib/state/schema.svelte.ts` (new)

### Tasks
- [ ] Define schema state store using Svelte 5 Runes:
  - `schemas: IfcValidationSchemaType[]` — list of schemas.
  - `activeSchema: IfcValidationSchemaType | null` — currently selected schema.
  - `rules: IfcValidationRule[]` — rules for active schema.
  - `validationResults: ValidationRunResult | null` — latest run results.
  - `loading: boolean`, `error: string | null`.
- [ ] Functions: `loadSchemas(branchId)`, `selectSchema(globalId)`, `loadRules(schemaGlobalId)`, `runValidation(schemaGlobalId, branchId)`.

**File:** `apps/web/src/lib/search/protocol.ts` (extend, or new `schema/protocol.ts`)

### Tasks
- [ ] Define BroadcastChannel protocol types for the Schema popup:
  - `SCHEMA_CHANNEL = 'bimatlas-schema'`
  - Message types: `schema:context`, `schema:select`, `schema:results`.

**File:** `apps/web/src/routes/+page.svelte` (modify)

### Tasks
- [ ] Add "Schema" button to the sidebar/dashboard alongside existing Graph/Search/Table buttons.
- [ ] Button opens `/schema` in a popup window (same `window.open` pattern as other popups).

---

## Step 10: Backend Tests

**File:** `apps/api/tests/test_validation.py` (new)

### Tasks
- [ ] Test `create_validation_entity` for IfcValidation, IfcValidationSchema, IfcValidationResult.
- [ ] Test `update_validation_entity` (SCD Type 2 close + new row).
- [ ] Test `delete_validation_entity` (SCD Type 2 close).
- [ ] Test `fetch_validation_entities` with class filter and revision scoping.
- [ ] Test graph edge operations: `link_rule_to_schema`, `unlink_rule_from_schema`, `get_rules_for_schema`.
- [ ] Test `evaluate_rule` with:
  - Simple attribute check (property exists, value equals).
  - Inheritance-expanded target class.
  - Subgraph-scoped check (spatial containment).
- [ ] Test `run_validation` end-to-end (create schema, link rules, run, verify results).
- [ ] Test GraphQL mutations: `createValidationSchema`, `createValidationRule`, `linkRuleToSchema`, `runValidation`.
- [ ] Test GraphQL queries: `validationSchemas`, `validationRules`, `validationResults`.

### Constraint
- Use the existing `conftest.py` fixtures (branch, revision, ifc_schema_seeded).
- Create test IFC entities (IfcWall, IfcSpace, etc.) to validate against.
- Use the `bimatlas_test` graph for AGE tests.

---

## Step 11: Verification & Manual Testing

### Tasks
- [ ] Run full backend test suite: `cd apps/api && source .venv/bin/activate && ./run_tests.sh`
- [ ] Run linting: `cd apps/api && source .venv/bin/activate && ruff check .`
- [ ] Start services and manually verify Schema Browser UI (if frontend components are built).
- [ ] Verify GraphQL playground at `http://localhost:8000/graphql`:
  - Create a validation schema.
  - Create a validation rule.
  - Link rule to schema.
  - Run validation against a branch.
  - Query results.

---

## Data Flow Diagram

```
User (Schema Browser UI)
    │
    ├─── Browse schemas ──────► GraphQL: validationSchemas(branchId)
    │                                  │
    │                                  ▼
    │                           ifc_entity WHERE ifc_class = 'IfcValidationSchema'
    │
    ├─── View rules ──────────► GraphQL: validationRules(schemaGlobalId)
    │                                  │
    │                                  ▼
    │                           AGE: IfcRelValidationToSchema edges → ifc_entity rules
    │
    ├─── Create rule ─────────► GraphQL: createValidationRule(...)
    │                                  │
    │                                  ▼
    │                           INSERT ifc_entity (IfcValidation) + CREATE AGE node
    │
    ├─── Link rule to schema ─► GraphQL: linkRuleToSchema(...)
    │                                  │
    │                                  ▼
    │                           CREATE AGE edge (IfcRelValidationToSchema)
    │
    └─── Run validation ──────► GraphQL: runValidation(schemaGlobalId, branchId)
                                       │
                                       ▼
                                Validation Engine:
                                  1. Fetch schema entity
                                  2. Get linked rule global_ids (AGE query)
                                  3. Fetch rule entities (ifc_entity)
                                  4. For each rule:
                                     a. Resolve target classes (inheritance)
                                     b. Apply spatial context (Cypher traversal)
                                     c. Fetch target entities
                                     d. Evaluate conditions (Python)
                                     e. Collect violations
                                  5. Aggregate results
                                  6. Store IfcValidationResult entity
                                  7. Return results via GraphQL
```

## Component Breakdown — Schema Browser UI

```
/schema (popup page)
├── +layout.svelte          ← BroadcastChannel setup, context sync
├── +page.svelte            ← Two-panel layout
│   ├── SchemaList.svelte   ← Left panel: schema list + "New" button
│   └── SchemaDetail.svelte ← Right panel: schema info + rules list
│       ├── RuleEditor.svelte   ← Modal/inline rule creation/editing
│       └── ValidationRunner.svelte ← Run validation + results display
```

State flow: `schema.svelte.ts` (Runes) ← GraphQL (urql) ← API ← DB/AGE
