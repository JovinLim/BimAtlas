"""MCP tool interface stubs for validation operations.

These functions are designed to be registered with an MCP server for
LlamaIndex agent usage. Each function delegates to the core validation
service layer and returns JSON-serializable dicts.
"""

from __future__ import annotations

from ...db import get_latest_revision_seq
from ..graph.age_client import get_entities_in_spatial_scope
from ..validation.engine import (
    run_validation_by_uploaded_schema as engine_run_validation_by_uploaded_schema,
)


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
    schema_id: str,
    revision: int | None = None,
) -> dict:
    """MCP tool: Execute validation rules from an uploaded IFC schema against a branch.

    Each rule's includeSubclasses flag (in rule_schema) controls whether it
    applies to the target class only or to the target and its subclasses.

    Returns a summary dict with error/warning/info counts and per-rule results.
    """
    result = engine_run_validation_by_uploaded_schema(schema_id, branch_id, revision)
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


def list_uploaded_schemas() -> list[dict]:
    """MCP tool: List all uploaded IFC schemas.

    Returns a list of dicts with ``schema_id``, ``version_name``, ``rule_count``.
    """
    from ...db import fetch_all_ifc_schemas

    rows = fetch_all_ifc_schemas()
    return [
        {
            "schema_id": r["schema_id"],
            "version_name": r["version_name"],
            "rule_count": r["rule_count"],
        }
        for r in rows
    ]
