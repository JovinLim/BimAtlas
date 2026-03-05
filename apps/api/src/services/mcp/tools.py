"""MCP tool interface stubs for validation operations.

These functions are designed to be registered with an MCP server for
LlamaIndex agent usage. Each function delegates to the core validation
service layer and returns JSON-serializable dicts.
"""

from __future__ import annotations

from ...db import (
    create_validation_entity,
    create_validation_revision,
    fetch_validation_entities,
    get_latest_revision_seq,
)
from ..graph.age_client import (
    create_validation_node,
    get_entities_in_spatial_scope,
    link_rule_to_schema,
)
from ..validation.engine import run_validation as engine_run_validation


def create_subgraph_rule(
    branch_id: str,
    name: str,
    target_class: str,
    conditions: list[dict],
    spatial_context: dict | None = None,
    severity: str = "Error",
    schema_global_id: str | None = None,
) -> dict:
    """MCP tool: Create a validation rule with optional subgraph scope.

    Parameters
    ----------
    branch_id : str
        Target branch UUID.
    name : str
        Human-readable rule name.
    target_class : str
        IFC class to validate (e.g. ``"IfcWall"``).
    conditions : list[dict]
        List of condition dicts with ``path``, ``operator``, and ``value``.
    spatial_context : dict, optional
        Subgraph scope: ``traversal``, ``scope_class``, ``scope_name``,
        ``scope_global_id``.
    severity : str
        ``"Error"``, ``"Warning"``, or ``"Info"``.
    schema_global_id : str, optional
        If provided, link the new rule to this schema.

    Returns
    -------
    dict
        Created rule entity with ``ifc_global_id`` and ``attributes``.
    """
    attrs: dict = {
        "Name": name,
        "RuleType": "attribute_check",
        "TargetClass": target_class,
        "Severity": severity,
        "Conditions": conditions,
    }
    if spatial_context:
        attrs["SpatialContext"] = spatial_context

    rev_info = create_validation_revision(branch_id, f"MCP: create rule {name}")
    row = create_validation_entity(
        branch_id, rev_info["revision_id"], "IfcValidation", attrs,
    )

    try:
        create_validation_node(
            "IfcValidation", row["ifc_global_id"],
            name, rev_info["revision_seq"], branch_id,
        )
    except Exception:
        pass

    if schema_global_id:
        try:
            link_rule_to_schema(
                row["ifc_global_id"], schema_global_id,
                rev_info["revision_seq"], branch_id,
            )
        except Exception:
            pass

    return {
        "ifc_global_id": row["ifc_global_id"],
        "ifc_class": row["ifc_class"],
        "attributes": row.get("attributes"),
    }


def query_spatial_context(
    branch_id: str,
    scope_class: str,
    scope_name: str,
    target_class: str | None = None,
    revision: int | None = None,
) -> list[dict]:
    """MCP tool: Query entities within a spatial context.

    Returns a list of dicts with ``global_id`` for entities contained
    in the specified spatial container.
    """
    rev = revision or get_latest_revision_seq(branch_id)
    if rev is None:
        return []

    gids = get_entities_in_spatial_scope(
        scope_global_id=None,
        scope_name=scope_name,
        rev=rev,
        branch_id=branch_id,
    )

    if target_class and gids:
        from ...db import fetch_entities_at_revision
        entities = fetch_entities_at_revision(rev, branch_id, ifc_class=target_class)
        entity_gids = {e["ifc_global_id"] for e in entities}
        gids = [g for g in gids if g in entity_gids]

    return [{"global_id": g} for g in gids]


def mcp_run_validation(
    branch_id: str,
    schema_global_id: str,
    revision: int | None = None,
) -> dict:
    """MCP tool: Execute a validation schema against a branch.

    Returns a summary dict with error/warning/info counts and per-rule results.
    """
    result = engine_run_validation(schema_global_id, branch_id, revision)
    return {
        "schema_global_id": result.schema_global_id,
        "schema_name": result.schema_name,
        "branch_id": result.branch_id,
        "revision_seq": result.revision_seq,
        "summary": result.summary,
        "results": [
            {
                "rule_global_id": r.rule_global_id,
                "rule_name": r.rule_name,
                "severity": r.severity,
                "passed": r.passed,
                "violation_count": len(r.violations),
            }
            for r in result.results
        ],
    }


def list_validation_schemas(
    branch_id: str,
    revision: int | None = None,
) -> list[dict]:
    """MCP tool: List all validation schemas on a branch.

    Returns a list of dicts with ``global_id``, ``name``, ``description``.
    """
    rows = fetch_validation_entities(branch_id, "IfcValidationSchema", revision)
    result = []
    for row in rows:
        attrs = row.get("attributes") or {}
        if isinstance(attrs, str):
            import json
            attrs = json.loads(attrs)
        result.append({
            "global_id": row["ifc_global_id"],
            "name": attrs.get("Name", ""),
            "description": attrs.get("Description"),
            "version": attrs.get("Version"),
            "is_active": attrs.get("IsActive", True),
        })
    return result
