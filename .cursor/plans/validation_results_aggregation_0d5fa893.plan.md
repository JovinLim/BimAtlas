---
name: Validation Results Aggregation
overview: Implement a write-optimized validation result store in `ifc_entity` and a read-aggregated materialized view that injects `attributes.Validations` for entity consumers (3D viewer + spreadsheet), while also exposing rule-centric data for the validation viewer.
todos:
  - id: db-contract-and-indexes
    content: Add `validation_rules.version` lifecycle and define `IfcValidationResults` payload with `rule_version`; add partial GIN + run-scope btree indexes and schema updates.
    status: completed
  - id: materialized-view
    content: Create `mv_entity_validations`, unique MV index for concurrent refresh, and wire refresh trigger strategy after validation runs.
    status: completed
  - id: backend-write-path
    content: Refactor validation engine/db helpers to persist one result entity per rule and enforce once-per-revision schema execution.
    status: completed
  - id: backend-read-path
    content: Inject `attributes.Validations` into entity reads and expose rule-centric validation query/resolver output for frontend.
    status: completed
  - id: frontend-consumers
    content: Update Attribute panel, table ENTITY.Validations column flow, and validation page expandable rule table UI.
    status: completed
  - id: verification
    content: Run backend tests and manual UI verification for 3D panel, spreadsheet formulas, and validation viewer expansion.
    status: completed
isProject: false
---

# Validation Results Storage & Aggregation Plan

## Scope and Existing Baseline

- Extend the existing validation framework (currently storing `IfcValidationResult`) to persist **per-rule run artifacts** as `ifc_entity` rows using class `IfcValidationResults` (plural) with rule-level pass/fail entity arrays.
- Introduce rule versioning in the rule-definition table (`validation_rule` in codebase; equivalent to `validation_rules` in product language): edits are append-only inserts with incremented `version`, and previous row is marked `is_active = false`.
- Reuse SCD Type 2 conventions and AGE sanitization utilities (`_validate_id`, `_validate_label`, `_escape_cypher_string`) when traversals are needed.
- Primary implementation files:
  - Backend DB/helpers: [/home/jovin/projects/BimAtlas/apps/api/src/db.py](/home/jovin/projects/BimAtlas/apps/api/src/db.py)
  - Validation engine: [/home/jovin/projects/BimAtlas/apps/api/src/services/validation/engine.py](/home/jovin/projects/BimAtlas/apps/api/src/services/validation/engine.py)
  - GraphQL resolvers/types: [/home/jovin/projects/BimAtlas/apps/api/src/schema/queries.py](/home/jovin/projects/BimAtlas/apps/api/src/schema/queries.py), [/home/jovin/projects/BimAtlas/apps/api/src/schema/ifc_types.py](/home/jovin/projects/BimAtlas/apps/api/src/schema/ifc_types.py)
  - DB bootstrap/test schema: [/home/jovin/projects/BimAtlas/infra/init-age.sql](/home/jovin/projects/BimAtlas/infra/init-age.sql), [/home/jovin/projects/BimAtlas/apps/api/tests/conftest.py](/home/jovin/projects/BimAtlas/apps/api/tests/conftest.py)
  - Frontend consumers: [/home/jovin/projects/BimAtlas/apps/web/src/lib/ui/AttributePanelContent.svelte](/home/jovin/projects/BimAtlas/apps/web/src/lib/ui/AttributePanelContent.svelte), [/home/jovin/projects/BimAtlas/apps/web/src/routes/table/+page.svelte](/home/jovin/projects/BimAtlas/apps/web/src/routes/table/+page.svelte), [/home/jovin/projects/BimAtlas/apps/web/src/routes/validation/+page.svelte](/home/jovin/projects/BimAtlas/apps/web/src/routes/validation/+page.svelte), [/home/jovin/projects/BimAtlas/apps/web/src/lib/api/client.ts](/home/jovin/projects/BimAtlas/apps/web/src/lib/api/client.ts)

## Phase 1: Database Setup (PostgreSQL)

### 1) Define storage contract for `IfcValidationResults`

- Store one row per `(branch_id, target_revision_seq, schema_global_id, rule_id)` in `ifc_entity`:
  - `ifc_class = 'IfcValidationResults'`
  - `attributes` shape (version-aware):
    - `SchemaGlobalId`, `SchemaName`, `TargetRevisionSeq`
    - `rule_id`, `rule_version`
    - `results.failed_global_ids: string[]`
    - `results.passed_global_ids: string[]`
    - optional denormalized display fields (`RuleName`, `Severity`) for debugging
- Keep SCD semantics: each write linked via `created_in_revision_id`; avoid direct updates of existing rows.

### 1.1) Rule table versioning contract

- Add `version INTEGER NOT NULL DEFAULT 1` to `validation_rule`.
- Add unique guardrails:
  - unique active version per logical rule id (`rule_id`, `version`)
  - partial uniqueness for exactly one active row per logical rule key.
- Update edit semantics:
  - “edit rule” becomes transaction: `UPDATE old_row SET is_active = false` + `INSERT new_row(version = old.version + 1, is_active = true)`.
- Keep reads for execution scoped to active versions by default, with explicit version lookup for historical joins.

### 2) Indexing strategy (write-optimized + reverse lookups)

- Add/confirm these indexes:
  - Existing broad JSONB GIN remains: `idx_ifc_entity_attributes`.
  - Add partial GIN for validation payloads only:
    - `CREATE INDEX idx_ifc_entity_validation_attrs_gin ON ifc_entity USING GIN (attributes jsonb_path_ops) WHERE ifc_class = 'IfcValidationResults' AND obsoleted_in_revision_id IS NULL;`
  - Add btree accelerator for run filters:
    - `CREATE INDEX idx_ifc_entity_validation_run ON ifc_entity (branch_id, ((attributes->>'TargetRevisionSeq')::int), (attributes->>'SchemaGlobalId'), (attributes->>'RuleGlobalId')) WHERE ifc_class = 'IfcValidationResults' AND obsoleted_in_revision_id IS NULL;`
- Rationale: btree handles run-scoped scans; partial GIN handles JSON/containment queries without penalizing non-validation rows.

### 3) Build read-aggregated materialized view

- Create MV that pivots rule rows to entity-centric JSON for frontend consumption, and joins rule definitions for version freshness:

```sql
CREATE MATERIALIZED VIEW mv_entity_validations AS
WITH validation_rows AS (
  SELECT
    e.branch_id,
    (e.attributes->>'TargetRevisionSeq')::int AS revision_seq,
    e.attributes->>'rule_id' AS rule_id,
    (e.attributes->>'rule_version')::int AS rule_version,
    vr.name AS rule_name,
    vr.severity::text AS severity,
    jsonb_array_elements_text(COALESCE(e.attributes->'results'->'failed_global_ids', '[]'::jsonb)) AS entity_global_id,
    false AS passed,
    CASE WHEN (e.attributes->>'rule_version')::int = vr.version THEN 'fresh' ELSE 'stale' END AS status
  FROM ifc_entity e
  JOIN validation_rule vr
    ON vr.rule_id::text = e.attributes->>'rule_id'
   AND vr.is_active = true
  WHERE e.ifc_class = 'IfcValidationResults'
    AND e.obsoleted_in_revision_id IS NULL

  UNION ALL

  SELECT
    e.branch_id,
    (e.attributes->>'TargetRevisionSeq')::int AS revision_seq,
    e.attributes->>'rule_id' AS rule_id,
    (e.attributes->>'rule_version')::int AS rule_version,
    vr.name AS rule_name,
    vr.severity::text AS severity,
    jsonb_array_elements_text(COALESCE(e.attributes->'results'->'passed_global_ids', '[]'::jsonb)) AS entity_global_id,
    true AS passed,
    CASE WHEN (e.attributes->>'rule_version')::int = vr.version THEN 'fresh' ELSE 'stale' END AS status
  FROM ifc_entity e
  JOIN validation_rule vr
    ON vr.rule_id::text = e.attributes->>'rule_id'
   AND vr.is_active = true
  WHERE e.ifc_class = 'IfcValidationResults'
    AND e.obsoleted_in_revision_id IS NULL
)
SELECT
  branch_id,
  revision_seq,
  entity_global_id,
  jsonb_object_agg(
    rule_id,
    jsonb_build_object(
      'ruleName', rule_name,
      'severity', severity,
      'passed', passed,
      'status', status
    )
  ) AS validations
FROM validation_rows
GROUP BY branch_id, revision_seq, entity_global_id;

CREATE UNIQUE INDEX idx_mv_entity_validations_key
  ON mv_entity_validations (branch_id, revision_seq, entity_global_id);
```

- Chosen mismatch behavior: **Option B** — stale rows remain visible with `status: "stale"` so the frontend can show “Needs Rerun”.

### 4) Entity attributes injection query contract

- For entity fetches, append validations at read time:
  - `jsonb_set(COALESCE(e.attributes,'{}'::jsonb), '{Validations}', COALESCE(mv.validations,'{}'::jsonb), true)`
- Apply in core entity query paths used by `ifcProduct`, `ifcProducts`, and `/table/entity-attributes` so `ENTITY.Validations.` works with no frontend schema branching.

### 5) Refresh strategy after schema runs

- After run writes complete, trigger `REFRESH MATERIALIZED VIEW CONCURRENTLY mv_entity_validations` in a background task.
- Add a light `validation_refresh_state` table (or in-memory debounce) to coalesce multiple run triggers into one refresh window.
- During refresh lag, backend read path for the just-run `(branch_id, revision_seq)` may optionally execute on-the-fly aggregation fallback for strict freshness.

## Phase 2: Backend API (Python)

### 6) Write pipeline for per-rule result entities

- In validation engine:
  - Replace single summary-row persistence with per-rule `IfcValidationResults` writes.
  - Persist `rule_version` captured from the active rule row at execution time.
  - Enforce “run once per revision/schema” by checking existing rows keyed by `SchemaGlobalId + TargetRevisionSeq`.
  - Preserve current result DTOs for API compatibility while source changes underneath.
- Update helpers in `db.py`:
  - expand allowed classes to include `IfcValidationResults`
  - add `fetch_validation_rule_results(branch_id, revision_seq, schema_global_id?)`
  - add versioned rule update helper (deactivate old + insert new version)
  - add helper to enqueue/trigger MV refresh.

### 7) Read APIs for aggregated entity and raw rule views

- GraphQL entity resolvers:
  - Ensure `ifcProduct` and `ifcProducts` return `attributes.Validations` from MV-enriched query.
- Validation-specific GraphQL:
  - Keep existing `validationResults` compatibility, but source it from per-rule entities (or expose v2 query for explicit rule rows).
  - Add/extend query for validation viewer table shape:
    - grouped by rule with counts and expandable violating entity IDs.
- REST `/table/entity-attributes`:
  - Ensure requested top-level `Validations` path is returned from injected attributes.

### 8) Tests (backend)

- DB tests for index/MV creation and refresh behavior.
- Engine tests:
  - writes one entity per rule
  - prevents duplicate rerun per revision
  - stores pass/fail arrays accurately.
- Resolver tests:
  - selected entity includes `attributes.Validations`
  - validation viewer query returns grouped+expandable data.
- Keep constraints explicit in tests:
  - no `validation_rule` mutations for result storage
  - SCD IDs and revision linkage always populated.

## Phase 3: Frontend Implementation (Svelte)

### 9) Shared client/state updates

- Extend GraphQL docs in `client.ts`:
  - include `attributes` (with `Validations`) where needed
  - add rule-table query shape for validation page expansion.
- Keep existing context flow (`branchId`, `revision`) and BroadcastChannel patterns unchanged.

### 10) 3D viewer entity panel (`AttributePanelContent`)

- Add a “Validations” section under Attributes:
  - list all rules for selected entity from `product.attributes.Validations`
  - show status badge (pass/fail) + severity + rule name + stale indicator (`Needs Rerun` when `status === 'stale'`)
  - include empty state when none.
- Preserve current non-blocking behavior if API is unavailable.

### 11) Spreadsheet formula support (`/table`)

- Keep formula parser unchanged (already resolves nested `ENTITY.`).
- Ensure data load path fetches `Validations` key when any header formula path starts with `ENTITY.Validations`.
- Document examples in UI placeholder/help:
  - `=ENTITY.Validations.<RuleId>.passed`
  - `=ENTITY.Validations.<RuleId>.severity`
  - `=ENTITY.Validations.<RuleId>.status`

### 12) Validation viewer (`/validation`)

- Replace/extend cards with tabular rule-centric view:
  - rows: rule, severity, pass/fail counts, fail count
  - expandable panel per row listing violating entity IDs/classes/messages.
- Add filters (schema, severity, pass/fail) client-side for responsiveness.

## Phase 4: Rollout & Verification

### 13) Migration + deployment sequencing

- Apply SQL migration (indexes + MV + unique index).
- Deploy backend write/read changes.
- Deploy frontend updates.
- Backfill: run one-time refresh to populate MV for historical `IfcValidationResults` rows.

### 14) Final validation step (required)

- Backend:
  - run API test suite including validation tests.
  - verify EXPLAIN plans for MV and rule lookup queries (index hit expected).
- Frontend:
  - manual verify in 3D entity panel, table formula columns, and expandable validation viewer.
- Acceptance checks:
  - each schema executes once per revision
  - each validation result stores `rule_version` matching execution-time active rule
  - selected entity shows rule results
  - stale results are visible with `status: "stale"` and frontend renders `Needs Rerun`
  - `ENTITY.Attributes.Validations.` formulas evaluate
  - validation viewer expands to violating entities.
