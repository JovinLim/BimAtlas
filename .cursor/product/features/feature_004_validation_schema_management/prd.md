---
feature_id: "FEAT-004"
status: "draft"
priority: "high"
---

# Feature: Validation Schema Management & Subgraph Validation Engine

## 1. Problem Statement

BimAtlas users need the ability to define, organize, and execute validation rules against IFC models—including complex rules that depend on spatial and functional relationships (subgraph validation). Currently, the `validation_rule` table stores IFC schema metadata (inheritance trees, required attributes) used for class resolution, but there is no system for user-defined validation rules, no grouping mechanism (schemas), and no UI for browsing or managing them. The system must treat `IfcValidation` and `IfcValidationSchema` as first-class graph citizens stored in `ifc_entity`, leverage the Apache AGE graph for relationship-aware rule evaluation, and expose all operations via GraphQL and MCP for agentic workflows.

## 2. Data Architecture: "Everything is an Entity"

### IfcValidation Entity
- Stored in the `ifc_entity` table with `ifc_class = 'IfcValidation'`.
- Inherits from IfcRoot (has `ifc_global_id`, `Name`, `Description` in `attributes`).
- The `attributes` JSONB field stores the validation logic:
  ```json
  {
    "Name": "Wall Fire Rating Check",
    "Description": "Ensure fire rating is 2hr",
    "RuleType": "attribute_check",
    "TargetClass": "IfcWall",
    "Severity": "Error",
    "Conditions": [
      {
        "path": "PropertySets.Pset_WallCommon.FireRating",
        "operator": "equals",
        "value": "2hr"
      }
    ],
    "SpatialContext": {
      "traversal": "IfcRelContainedInSpatialStructure",
      "scope_class": "IfcSpace",
      "scope_name": "Room X"
    }
  }
  ```

### IfcValidationSchema Entity
- Stored in `ifc_entity` with `ifc_class = 'IfcValidationSchema'`.
- Inherits from IfcRoot. Acts as a named container for grouped validation rules.
- `attributes` JSONB stores metadata:
  ```json
  {
    "Name": "Fire Safety Schema",
    "Description": "All fire safety validation rules",
    "Version": "1.0",
    "IsActive": true
  }
  ```

### Relational Logic (Graph Edges)
- Rules are linked to schemas via `IfcRelValidationToSchema` edges in the AGE graph (not hardcoded FKs).
- This edge connects an `IfcValidation` node to an `IfcValidationSchema` node.
- Standard branch/revision scoping applies (`valid_from_rev`, `valid_to_rev`, `branch_id`).

### Rule Persistence & Scoping
- Validation entities are project-scoped, typically stored on the `main` branch.
- They participate in the SCD Type 2 versioning system like all other entities.
- `IfcAgent` entities (LLM configuration) follow the same pattern (future scope).

## 3. Functional Requirements

### Req 1 (Attribute & Property Checks)
- Validate existence and values of Pset properties and EXPRESS attributes.
- Operators: `equals`, `not_equals`, `contains`, `exists`, `not_exists`, `greater_than`, `less_than`, `matches` (regex).
- Nested key paths (e.g., `PropertySets.Pset_WallCommon.FireRating`).

### Req 2 (Inheritance Checks)
- Validate based on IFC class hierarchy using `ifc_schema_loader.get_descendants()`.
- Rule: "Target must be a subtype of IfcWall" → resolves all concrete descendants.

### Req 3 (Subgraph/Relationship Validation)
- Rules can specify a `SpatialContext` block defining graph traversal scope.
- Supported traversals: `IfcRelContainedInSpatialStructure`, `IfcRelAggregates`, `IfcRelConnectsElements`, `IfcRelVoidsElement`, `IfcRelFillsElement`, `IfcRelDefinesByType`.
- Example: "All IfcWall entities contained in IfcSpace 'Room X' must have Pset_WallCommon.FireRating = '2hr'".
- Implementation: Cypher query traverses the specified relationship to identify target entities, then attribute checks run against the filtered set.

### Req 4 (Severity Levels)
- Each rule carries a severity: `Error`, `Warning`, or `Info`.
- Results are grouped by severity in validation run output.

### Req 5 (Validation Run & Results)
- A validation run applies all rules in a schema to a specific branch at the latest (or specified) revision.
- Results stored as an `IfcValidationResult` entity (ifc_class = 'IfcValidationResult') containing a JSONB summary of pass/fail per rule, with affected entity global IDs.
- GraphQL mutation: `runValidation(schemaGlobalId, branchId, revision?)` → returns validation results.

### Req 6 (CRUD via GraphQL)
- Mutations: `createValidationRule`, `updateValidationRule`, `deleteValidationRule`.
- Mutations: `createValidationSchema`, `updateValidationSchema`, `deleteValidationSchema`.
- Mutations: `linkRuleToSchema`, `unlinkRuleFromSchema`.
- Queries: `validationSchemas(branchId)`, `validationRules(schemaGlobalId, branchId)`, `validationResults(branchId)`.

### Req 7 (MCP Tool Expansion)
- MCP tools: `create_subgraph_rule`, `query_spatial_context`, `run_validation`, `list_validation_schemas`.
- These tools allow the LlamaIndex agent to create rules from natural language requests and trigger validation runs.

## 4. Frontend: Schema Browser Component

### Entry Point
- A "Schema" button on the main dashboard (next to existing Graph/Search/Table buttons).
- Opens as a popup browser tab (consistent with existing popup pattern).

### UI Components
- **SchemaList**: Browse all `IfcValidationSchema` entities for the active branch.
- **SchemaDetail**: Drill-down view showing all linked `IfcValidation` rules.
- **RuleEditor**: Form-based logic builder for creating/editing rules (target class selector, condition builder, spatial context selector, severity picker).
- **ValidationRunner**: Branch selector + "Apply" button to trigger a validation run. Displays results summary.

### State Management
- Svelte 5 Runes (`$state`, `$derived`, `$effect`).
- BroadcastChannel for cross-window sync with the main view (`bimatlas-schema` channel).
- Schema/rule data fetched via GraphQL (urql client).

## 5. Out of Scope (Strict Constraints)

- Do not modify the existing `validation_rule` table; it remains dedicated to IFC schema metadata (inheritance, required attributes).
- Do not implement a full MCP server or LlamaIndex agent in this phase; define the tool interfaces and stubs only.
- Do not implement merge conflict resolution for validation entities (standard SCD merge path applies).
- Do not store validation results as separate relational tables; use the entity-based pattern.
- Do not execute raw user-provided Cypher strings; all graph queries must be parameterized via the existing age_client pattern.

## 6. Success Criteria

- [ ] `IfcValidation` and `IfcValidationSchema` entities can be created, read, updated, and deleted via GraphQL mutations.
- [ ] Rules can be linked to schemas via `IfcRelValidationToSchema` graph edges.
- [ ] A validation run against a branch evaluates all rules in a schema and returns per-rule pass/fail results with affected entity IDs.
- [ ] Subgraph validation (e.g., spatial containment scope) correctly filters target entities via Cypher traversal before applying attribute checks.
- [ ] The Schema Browser UI allows browsing schemas, viewing linked rules, creating/editing rules, and triggering validation runs.
- [ ] MCP tool interfaces are defined and stubbed for agentic workflows.
- [ ] All new backend functionality has passing tests.
