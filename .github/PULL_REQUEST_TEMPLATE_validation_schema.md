# feat: Validation Schema Management & Subgraph Validation Engine (FEAT-004)

## Summary

Implements the Validation Schema Management feature: user-defined validation rules and schemas stored as first-class graph entities in `ifc_entity`, with GraphQL CRUD, a Schema Browser UI, and MCP tool stubs for agentic workflows.

## Changes

### Backend (API)
- **DB / AGE:** Migration `008_validation_entity_labels.sql` adds vertex labels `IfcValidation`, `IfcValidationSchema`, `IfcValidationResult` and edge label `IfcRelValidationToSchema`
- **db.py:** CRUD for validation entities via `ifc_entity` table; `create_validation_entity`, `fetch_validation_entities`, `update_validation_entity`, `delete_validation_entity`
- **Graph:** AGE client helpers for validation labels; Cypher queries for rule–schema linking and subgraph traversal
- **Validation engine:** `engine_run_validation()` evaluates attribute checks, inheritance-aware rules, and spatial-context subgraph validation
- **GraphQL:** Types `IfcValidationSchemaType`, `IfcValidationType`, `IfcValidationResultType`; queries `validationSchemas`, `validationSchema`, `validationRules`, `validationResults`; mutations `createValidationSchema`, `updateValidationSchema`, `deleteValidationSchema`, `createValidationRule`, `updateValidationRule`, `deleteValidationRule`, `linkRuleToSchema`, `unlinkRuleFromSchema`, `runValidation`
- **MCP tools:** `run_validation`, `list_validation_schemas` (stubs for agent workflows)

### Frontend
- **Schema Browser:** New `/schema` route with SchemaList, SchemaDetail, RuleEditor, ValidationRunner
- **Entry point:** "Schema" button on main dashboard opens Schema Browser popup
- **API client:** GraphQL queries/mutations for validation schemas and rules

### Tests
- `test_validation.py`: Unit tests for validation entity CRUD, GraphQL mutations/queries, and validation engine behavior

## Testing

```bash
cd apps/api && source .venv/bin/activate && ./run_tests.sh
```

## Related

- PRD: `.cursor/product/features/feature_004_validation_schema_management/prd.md`
- Plan: `.cursor/plans/validation-schema-management_bfbf.plan.md`
