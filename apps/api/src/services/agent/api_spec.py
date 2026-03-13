"""Curated API discovery payload for autonomous agent workflows."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi import FastAPI


def _format_graphql_fields(fields: dict[str, Any]) -> list[dict[str, Any]]:
    formatted: list[dict[str, Any]] = []
    for field_name, field in sorted(fields.items(), key=lambda item: item[0]):
        args = {
            arg_name: str(arg.type)
            for arg_name, arg in sorted(field.args.items(), key=lambda item: item[0])
        }
        formatted.append(
            {
                "name": field_name,
                "args": args,
                "return_type": str(field.type),
            }
        )
    return formatted


def _graphql_examples() -> dict[str, Any]:
    return {
        "ifc_queries": {
            "ifc_products_by_class": {
                "query": (
                    "query($branchId: String!, $revision: Int, $ifcClass: String) { "
                    "ifcProducts(branchId: $branchId, revision: $revision, ifcClass: $ifcClass) { "
                    "globalId ifcClass name } }"
                ),
                "variables": {
                    "branchId": "CURRENT_BRANCH_ID",
                    "revision": None,
                    "ifcClass": "IfcWall",
                },
                "note": "Use ifcClass for exact match (e.g. IfcWall). For walls and subtypes use ifcClasses: [\"IfcWall\", \"IfcWallStandardCase\", \"IfcWallType\"].",
            },
            "ifc_products_count": {
                "query": (
                    "query($branchId: String!, $revision: Int, $ifcClasses: [String!]) { "
                    "ifcProducts(branchId: $branchId, revision: $revision, ifcClasses: $ifcClasses) { "
                    "globalId } }"
                ),
                "variables": {
                    "branchId": "CURRENT_BRANCH_ID",
                    "revision": None,
                    "ifcClasses": ["IfcWall", "IfcWallStandardCase", "IfcWallType"],
                },
                "note": "Returns list; count length for totals. Use ifcClasses for multiple types.",
            },
            "ifc_products_by_spatial_containment": {
                "query": (
                    "query($branchId: String!, $revision: Int, $ifcClass: String, "
                    "$relationTypes: [IfcRelationshipType!], $containedIn: String) { "
                    "ifcProducts(branchId: $branchId, revision: $revision, ifcClass: $ifcClass, "
                    "relationTypes: $relationTypes, containedIn: $containedIn) { "
                    "globalId name } }"
                ),
                "variables": {
                    "branchId": "CURRENT_BRANCH_ID",
                    "revision": None,
                    "ifcClass": "IfcWindow",
                    "relationTypes": ["IfcRelContainedInSpatialStructure"],
                    "containedIn": "Ground Floor",
                },
                "note": "Use IFC relation semantics first: set relationTypes to IfcRelContainedInSpatialStructure and then target the storey via containedIn (GlobalId or Name).",
            },
            "ifc_product_class_tree": {
                "query": (
                    "query($branchId: String!, $revision: Int) { "
                    "ifcProductClassTree(branchId: $branchId, revision: $revision) { "
                    "ifcClass children { ifcClass } } }"
                ),
                "variables": {"branchId": "CURRENT_BRANCH_ID", "revision": None},
                "note": "Shows IFC classes present in the model and their hierarchy.",
            },
        },
        "validation_schema_crud": {
            "list_uploaded_schemas": {
                "query": "query { uploadedSchemas { id versionName ruleCount projectIds } }",
            },
            "list_rules_for_schema": {
                "query": (
                    "query($schemaId: String!) { "
                    "validationRulesForUploadedSchema(schemaId: $schemaId) { "
                    "ruleId name targetIfcClass severity ruleSchemaJson "
                    "} }"
                ),
                "variables": {"schemaId": "schema-uuid"},
            },
            "create_uploaded_schema": {
                "query": (
                    "mutation($name: String!) { "
                    "createUploadedSchema(name: $name) { id versionName ruleCount } "
                    "}"
                ),
                "variables": {"name": "Fire_2026"},
            },
            "create_uploaded_schema_rule_required_attributes": {
                "query": (
                    "mutation($schemaId: String!, $name: String!, $targetIfcClass: String!, "
                    "$severity: String!, $ruleSchemaJson: String!) { "
                    "createUploadedSchemaRule(schemaId: $schemaId, name: $name, "
                    "targetIfcClass: $targetIfcClass, severity: $severity, "
                    "ruleSchemaJson: $ruleSchemaJson) { ruleId name severity } }"
                ),
                "variables": {
                    "schemaId": "schema-uuid",
                    "name": "Wall Fire Rating Required",
                    "targetIfcClass": "IfcWall",
                    "severity": "Error",
                    "ruleSchemaJson": (
                        '{"type":"required_attributes","effectiveRequiredAttributes":'
                        '["FireRating"]}'
                    ),
                },
            },
            "create_uploaded_schema_rule_attribute_check": {
                "query": (
                    "mutation($schemaId: String!, $name: String!, $targetIfcClass: String!, "
                    "$severity: String!, $ruleSchemaJson: String!) { "
                    "createUploadedSchemaRule(schemaId: $schemaId, name: $name, "
                    "targetIfcClass: $targetIfcClass, severity: $severity, "
                    "ruleSchemaJson: $ruleSchemaJson) { ruleId name severity } }"
                ),
                "variables": {
                    "schemaId": "schema-uuid",
                    "name": "Door Width Minimum",
                    "targetIfcClass": "IfcDoor",
                    "severity": "Warning",
                    "ruleSchemaJson": (
                        '{"type":"attribute_check","conditionLogic":"AND","conditions":['
                        '{"path":"OverallWidth","operator":"greater_than","value":0.9}'
                        "]}"
                    ),
                },
            },
            "update_uploaded_schema_rule": {
                "query": (
                    "mutation($ruleId: String!, $name: String!, $severity: String!, "
                    "$ruleSchemaJson: String!) { "
                    "updateUploadedSchemaRule(ruleId: $ruleId, name: $name, "
                    "severity: $severity, ruleSchemaJson: $ruleSchemaJson) }"
                ),
                "variables": {
                    "ruleId": "rule-uuid",
                    "name": "Updated Rule Name",
                    "severity": "Error",
                    "ruleSchemaJson": (
                        '{"type":"required_attributes","effectiveRequiredAttributes":'
                        '["FireRating","LoadBearing"]}'
                    ),
                },
            },
            "delete_uploaded_schema_rule": {
                "query": (
                    "mutation($ruleId: String!) { deleteUploadedSchemaRule(ruleId: $ruleId) }"
                ),
                "variables": {"ruleId": "rule-uuid"},
            },
            "run_validation_by_uploaded_schema": {
                "query": (
                    "mutation($branchId: String!, $schemaId: String!) { "
                    "runValidationByUploadedSchema(branchId: $branchId, schemaId: $schemaId) { "
                    "schemaGlobalId schemaName revisionSeq errorCount warningCount infoCount "
                    "} }"
                ),
                "variables": {"branchId": "branch-uuid", "schemaId": "schema-uuid"},
            },
        },
    }


def _ifc_cheat_sheet() -> dict[str, Any]:
    """IFC semantic mappings and guardrails for domain-safe filter construction."""
    return {
        "directive": (
            "ALWAYS read this cheat sheet before constructing GraphQL filters. "
            "Do NOT guess field names or relational paths. Use search_skills first, "
            "then ask_user_for_guidance if the path is unclear."
        ),
        "relational_paths": {
            "spatial_containment": {
                "description": "Elements contained in a spatial structure (e.g. storey, building)",
                "path": "IfcProduct -> IfcRelContainedInSpatialStructure -> IfcSpatialStructureElement",
                "target_classes": ["IfcBuildingStorey", "IfcBuilding", "IfcSite"],
                "note": "Preferred construction: relationTypes=[IfcRelContainedInSpatialStructure] + containedIn target (Name or GlobalId).",
            },
            "type_object": {
                "description": "Elements typed by an IfcTypeObject (e.g. IfcWallType)",
                "path": "IfcProduct -> IfcRelDefinesByType -> IfcTypeObject",
                "target_classes": ["IfcWallType", "IfcDoorType", "IfcWindowType"],
                "note": "Use relation mode for type-based filtering.",
            },
            "material": {
                "description": "Elements with material assignment",
                "path": "IfcProduct -> IfcRelAssociatesMaterial -> IfcMaterial",
                "note": "Material filtering may require IfcMaterialLayerSet or IfcMaterialConstituentSet.",
            },
        },
        "filter_modes": {
            "EXACT": "Exact string match. Use for attributes like Name, Tag.",
            "CONTAINS": "Substring match (ILIKE). Use for partial text search.",
            "class": "Filter by IFC class (ifcClass). Use exact class name.",
            "attribute": "Filter by JSONB attribute path. Paths are dot-separated (e.g. Name, FireRating).",
            "relation": "Filter by related entity. Requires relationTargetClass, relationTargetAttribute, relationTargetValue.",
        },
        "anti_patterns": [
            "Do NOT invent relationship names. Use only IfcRel* classes from this cheat sheet.",
            "Do NOT treat containedIn as a universal relation filter; it is spatial-only.",
            "For spatial containment, explicitly use IfcRelContainedInSpatialStructure relation semantics.",
        ],
        "query_construction_policy": {
            "relation_first": (
                "For relational intent, construct GraphQL using IFC relation concepts first "
                "(relationTypes and/or relation-mode filter sets)."
            ),
            "spatial": (
                "Spatial containment is a specific relation path: "
                "IfcRelContainedInSpatialStructure -> IfcSpatialStructureElement."
            ),
            "non_spatial_examples": [
                "IfcRelAggregates for decomposition/assembly relationships.",
                "IfcRelDefinesByType for type-object relationships.",
                "IfcRelAssociatesMaterial for material relationships.",
            ],
        },
        "filter_set_mutations": {
            "create_filter_set": "createFilterSet(branchId, name, logic, filters, filtersTree, color)",
            "apply_filter_sets": "applyFilterSets(branchId, filterSetIds, combinationLogic)",
            "note": "filters_tree uses canonical tree: { kind: 'group', op: 'ALL'|'ANY', children: [...] }.",
        },
    }


def build_agent_api_spec(app: FastAPI, strawberry_schema: Any) -> dict[str, Any]:
    """Build a curated API contract optimized for autonomous agent use."""
    openapi = deepcopy(app.openapi())
    paths = openapi.get("paths", {})
    curated_paths: dict[str, Any] = {}

    hidden_prefixes = (
        "/health",
        "/agent/configs",
        "/agent/chats",
        "/agent/context",
        "/agent/api-spec",
    )
    keep_paths = (
        "/graphql",
        "/upload-ifc",
        "/ifc-schema",
        "/table/entity-attributes",
        "/agent/skills",
        "/agent/skills/frontmatter",
        "/agent/skills/search",
    )
    for path, path_item in paths.items():
        if path.startswith(hidden_prefixes) and path not in keep_paths:
            continue
        curated_paths[path] = path_item

    if "/agent/upload" in curated_paths and "post" in curated_paths["/agent/upload"]:
        curated_paths["/agent/upload"]["post"]["x-agent-examples"] = {
            "multipart": {
                "fields": {
                    "session_id": "8f8bb275-7f74-4e0f-b9d8-e63812345678",
                    "file": "<binary pdf/csv/txt/json/xml/xlsx>",
                }
            }
        }
    if "/ifc-schema" in curated_paths and "post" in curated_paths["/ifc-schema"]:
        curated_paths["/ifc-schema"]["post"]["x-agent-examples"] = {
            "json": {
                "schema": "IFC4X3_ADD2",
                "entities": {"IfcWall": {"parent": "IfcBuildingElement", "attributes": []}},
            }
        }
    if "/table/entity-attributes" in curated_paths and "post" in curated_paths["/table/entity-attributes"]:
        curated_paths["/table/entity-attributes"]["post"]["x-agent-examples"] = {
            "json": {
                "branchId": "branch-uuid",
                "revision": None,
                "globalIds": ["2Q$2xR9Qv8xQf8C3MsABCD"],
                "paths": ["Name", "FireRating"],
            }
        }
    if "/agent/skills/frontmatter" in curated_paths and "get" in curated_paths["/agent/skills/frontmatter"]:
        curated_paths["/agent/skills/frontmatter"]["get"]["x-agent-examples"] = {
            "query": {"project_id": "PROJECT_ID", "branch_id": "BRANCH_ID", "limit": 50},
        }
    if "/agent/skills/search" in curated_paths and "post" in curated_paths["/agent/skills/search"]:
        curated_paths["/agent/skills/search"]["post"]["x-agent-examples"] = {
            "json": {
                "intent": "show me ground floor windows",
                "projectId": "PROJECT_ID",
                "branchId": "BRANCH_ID",
                "topK": 5,
                "apiKey": "<optional, uses OPENAI_API_KEY if omitted>",
            },
        }
    if "/agent/skills" in curated_paths and "post" in curated_paths["/agent/skills"]:
        curated_paths["/agent/skills"]["post"]["x-agent-examples"] = {
            "json": {
                "projectId": "PROJECT_ID",
                "title": "Ground floor windows",
                "intent": "filter windows by building storey",
                "frontmatter": {"ifcPath": "IfcRelContainedInSpatialStructure", "targetClass": "IfcBuildingStorey"},
                "contentMd": "## Relational path\n...",
                "branchId": "BRANCH_ID",
                "apiKey": "<optional>",
            },
        }

    graph_schema = getattr(strawberry_schema, "_schema", None)
    query_fields: list[dict[str, Any]] = []
    mutation_fields: list[dict[str, Any]] = []
    if graph_schema is not None:
        if getattr(graph_schema, "query_type", None):
            query_fields = _format_graphql_fields(graph_schema.query_type.fields)
        if getattr(graph_schema, "mutation_type", None):
            mutation_fields = _format_graphql_fields(graph_schema.mutation_type.fields)

    return {
        "title": openapi.get("info", {}).get("title", "BimAtlas API"),
        "version": openapi.get("info", {}).get("version", "unknown"),
        "description": (
            "Curated BimAtlas API contract for autonomous agent execution. "
            "Use GraphQL for rich model and schema CRUD."
        ),
        "base_path": "/",
        "paths": curated_paths,
        "graphql": {
            "endpoint": "/graphql",
            "queries": query_fields,
            "mutations": mutation_fields,
            "examples": _graphql_examples(),
        },
        "ifc_cheat_sheet": _ifc_cheat_sheet(),
    }
