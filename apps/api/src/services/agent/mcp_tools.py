"""MCP tool implementations for the Agentic Filtering Framework.

Each tool wraps existing DB functions and exposes them as callable functions
that LlamaIndex can bind as ``FunctionTool`` instances.  The tools operate
within a *context* (branch_id + optional revision) injected at agent
instantiation time.

Tools
-----
1. get_project_schema  – discover IFC classes, attributes, operators
2. create_filter_set   – create a named empty filter set
3. add_filter_condition – append a condition to an existing filter set
4. apply_filter_set_to_context – apply filter sets to a branch view
"""

from __future__ import annotations

import json
import logging
from functools import partial
from typing import Any, Optional
from uuid import UUID

from llama_index.core.tools import FunctionTool

from ...db import (
    apply_filter_sets as db_apply_filter_sets,
)
from ...db import (
    create_filter_set as db_create_filter_set,
)
from ...db import (
    fetch_applied_filter_sets as db_fetch_applied_filter_sets,
)
from ...db import (
    fetch_common_attribute_keys,
    fetch_distinct_ifc_classes_at_revision,
    fetch_entities_with_filter_sets,
    fetch_entity_count_at_revision,
    get_latest_revision_seq,
)
from ...db import (
    fetch_filter_set as db_fetch_filter_set,
)
from ...db import (
    update_filter_set as db_update_filter_set,
)
from ...schema.filter_operators import (
    CLASS_OPERATORS,
    NUMERIC_OPERATORS,
    STRING_OPERATORS,
    is_valid_operator,
    value_required_for_operator,
)
from ...schema.ifc_enums import IfcRelationshipType
from .events import event_bus

logger = logging.getLogger("bimatlas.agent")
VALID_VALUE_TYPES = {"string", "numeric", "object"}


def _normalize_value_type(
    value_type: str | None,
    attribute: str | None,
    operator: str,
) -> str | None:
    """Normalize and infer value type for attribute filters."""
    if value_type is None:
        if operator in NUMERIC_OPERATORS:
            return "numeric"
        if (attribute or "").strip().lower() == "propertysets":
            # PropertySets commonly needs object-key matching (e.g. Pset_WallCommon).
            return "object"
        return None

    normalized = str(value_type).strip().lower()
    aliases = {
        "number": "numeric",
        "text": "string",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in VALID_VALUE_TYPES:
        allowed = ", ".join(sorted(VALID_VALUE_TYPES))
        raise ValueError(
            f"Invalid value_type: {value_type}. Must be one of: {allowed}.",
        )
    return normalized


def _resolve_rev(branch_id: str, revision: int | None) -> int:
    if revision is not None:
        return revision
    rev = get_latest_revision_seq(branch_id)
    if rev is None:
        raise ValueError("No revisions on this branch")
    return rev


def _validate_uuid(value: str, label: str = "ID") -> None:
    try:
        UUID(value)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid {label}: {value}")


# ---------------------------------------------------------------------------
# Tool 1: get_project_schema
# ---------------------------------------------------------------------------

def get_project_schema(
    branch_id: str,
    revision: Optional[int] = None,
) -> dict[str, Any]:
    """Return the IFC schema context for a branch: unique classes, common
    attribute keys, available filter operators, relationship types, and a
    class hierarchy map.  Call this FIRST to understand what data exists
    before creating filters.
    """
    _validate_uuid(branch_id, "branch_id")
    rev = _resolve_rev(branch_id, revision)

    ifc_classes = fetch_distinct_ifc_classes_at_revision(rev, branch_id)
    common_attrs = fetch_common_attribute_keys(rev, branch_id, limit=50)
    entity_count = fetch_entity_count_at_revision(rev, branch_id)

    hierarchy: dict[str, list[str]] = {}
    try:
        from ...schema import ifc_schema_loader
        for cls in ifc_classes:
            parents: list[str] = []
            current = cls
            while True:
                p = ifc_schema_loader.get_parent(current)
                if p is None:
                    break
                parents.append(p)
                current = p
            if parents:
                hierarchy[cls] = parents
    except Exception:
        pass

    rel_types = [e.value for e in IfcRelationshipType]

    return {
        "ifc_classes": sorted(ifc_classes),
        "ifc_class_hierarchy": hierarchy,
        "common_attributes": common_attrs,
        "attribute_value_types": sorted(VALID_VALUE_TYPES),
        "attribute_value_type_hints": {
            "PropertySets": "object",
        },
        "relationship_types": rel_types,
        "filter_operators": {
            "string": sorted(STRING_OPERATORS),
            "numeric": sorted(NUMERIC_OPERATORS),
            "class": sorted(CLASS_OPERATORS),
        },
        "entity_count": entity_count,
    }


# ---------------------------------------------------------------------------
# Tool 2: create_filter_set
# ---------------------------------------------------------------------------

def create_filter_set(
    branch_id: str,
    name: str,
    logic: str = "AND",
) -> dict[str, Any]:
    """Create a new empty named filter set on a branch.  Returns the filter
    set ID for subsequent add_filter_condition calls.

    Parameters
    ----------
    branch_id : UUID string of the target branch.
    name : Human-readable name (e.g. 'Fire-rated walls').
    logic : Intra-set logic for combining conditions ('AND' or 'OR').
    """
    _validate_uuid(branch_id, "branch_id")
    if logic not in ("AND", "OR"):
        logic = "AND"

    row = db_create_filter_set(branch_id, name, logic, filters_json=[])
    return {
        "filter_set_id": row["filter_set_id"],
        "name": row["name"],
        "logic": row["logic"],
        "filters": [],
    }


# ---------------------------------------------------------------------------
# Tool 3: add_filter_condition
# ---------------------------------------------------------------------------

def add_filter_condition(
    filter_set_id: str,
    mode: str,
    operator: str,
    ifc_class: Optional[str] = None,
    attribute: Optional[str] = None,
    value: Optional[str] = None,
    value_type: Optional[str] = None,
    relation: Optional[str] = None,
) -> dict[str, Any]:
    """Append a filter condition to an existing filter set.

    Parameters
    ----------
    filter_set_id : UUID of the filter set to modify.
    mode : 'class', 'attribute', or 'relation'.
    operator : The operator to apply (e.g. 'is', 'inherits_from', 'contains', 'gt').
    ifc_class : Required when mode='class'.
    attribute : Required when mode='attribute'.
    value : Comparison value (not needed for is_empty / is_not_empty).
    value_type : 'string', 'numeric', or 'object' (attribute mode only).
        Use 'object' to match nested object key names (e.g. PropertySets contains
        Pset_WallCommon). If omitted, numeric operators infer 'numeric', and
        PropertySets infers 'object'.
    relation : Required when mode='relation'.
    """
    _validate_uuid(filter_set_id, "filter_set_id")

    if mode not in ("class", "attribute", "relation"):
        raise ValueError(f"Invalid mode: {mode}. Must be 'class', 'attribute', or 'relation'.")

    if not is_valid_operator(mode, operator):
        raise ValueError(f"Invalid operator '{operator}' for mode '{mode}'.")

    if mode == "class" and not ifc_class:
        raise ValueError("ifc_class is required for mode='class'.")
    if mode == "attribute" and not attribute:
        raise ValueError("attribute is required for mode='attribute'.")
    if mode == "relation" and not relation:
        raise ValueError("relation is required for mode='relation'.")

    if mode == "attribute" and value_required_for_operator(operator) and not value:
        raise ValueError(f"value is required for operator '{operator}'.")

    existing = db_fetch_filter_set(filter_set_id)
    if existing is None:
        raise ValueError(f"Filter set {filter_set_id} not found.")

    filters = existing.get("filters") or []
    if isinstance(filters, str):
        filters = json.loads(filters)

    normalized_value_type: str | None = None
    if mode == "attribute":
        normalized_value_type = _normalize_value_type(value_type, attribute, operator)

    new_condition: dict[str, Any] = {"mode": mode, "operator": operator}
    if ifc_class:
        new_condition["ifcClass"] = ifc_class
    if attribute:
        new_condition["attribute"] = attribute
    if value is not None:
        new_condition["value"] = value
    if normalized_value_type:
        new_condition["valueType"] = normalized_value_type
    if relation:
        new_condition["relation"] = relation

    filters.append(new_condition)
    updated = db_update_filter_set(filter_set_id, filters_json=filters)
    if updated is None:
        raise ValueError(f"Failed to update filter set {filter_set_id}.")

    updated_filters = updated.get("filters") or []
    if isinstance(updated_filters, str):
        updated_filters = json.loads(updated_filters)

    return {
        "filter_set_id": updated["filter_set_id"],
        "name": updated["name"],
        "logic": updated["logic"],
        "filters": updated_filters,
        "condition_count": len(updated_filters),
    }


# ---------------------------------------------------------------------------
# Tool 4: apply_filter_set_to_context
# ---------------------------------------------------------------------------

def apply_filter_set_to_context(
    branch_id: str,
    filter_set_ids: list[str],
    combination_logic: str = "OR",
) -> dict[str, Any]:
    """Apply one or more filter sets to a branch, updating the active view.
    After application the frontend view refreshes to show only matching
    entities.

    Parameters
    ----------
    branch_id : UUID of the target branch.
    filter_set_ids : List of filter set UUIDs to apply.
    combination_logic : Always 'OR' (AND is disabled).
    """
    _validate_uuid(branch_id, "branch_id")
    for fs_id in filter_set_ids:
        _validate_uuid(fs_id, "filter_set_id")

    combination_logic = "OR"

    db_apply_filter_sets(branch_id, filter_set_ids, combination_logic)

    matched_count = 0
    try:
        applied = db_fetch_applied_filter_sets(branch_id)
        if applied["filter_sets"]:
            rev = _resolve_rev(branch_id, None)
            filter_sets_data = [
                {"logic": fs.get("logic", "AND"), "filters": fs.get("filters", [])}
                for fs in applied["filter_sets"]
            ]
            rows = fetch_entities_with_filter_sets(
                rev, branch_id, filter_sets_data,
                combination_logic=applied["combination_logic"],
            )
            matched_count = len(rows)
    except Exception:
        logger.warning("Could not count matched entities after filter application", exc_info=True)

    event_bus.publish_filter_applied(branch_id, filter_set_ids, matched_count)

    applied_summary = []
    for fs_id in filter_set_ids:
        fs = db_fetch_filter_set(fs_id)
        if fs:
            filters = fs.get("filters") or []
            if isinstance(filters, str):
                filters = json.loads(filters)
            applied_summary.append({
                "id": fs["filter_set_id"],
                "name": fs["name"],
                "condition_count": len(filters),
            })

    return {
        "applied_filter_sets": applied_summary,
        "combination_logic": combination_logic,
        "matched_entity_count": matched_count,
    }


# ---------------------------------------------------------------------------
# Tool registry — returns LlamaIndex FunctionTool wrappers with context bound
# ---------------------------------------------------------------------------

def get_agent_tools(branch_id: str, revision: int | None = None) -> list[FunctionTool]:
    """Return LlamaIndex FunctionTool wrappers with branch_id and revision bound.

    The branch_id and revision are injected at agent instantiation so the LLM
    does not need to provide them — it cannot know the correct values.
    """
    get_schema = partial(get_project_schema, branch_id, revision)
    create_fs = partial(create_filter_set, branch_id)
    apply_fs = partial(apply_filter_set_to_context, branch_id)

    return [
        FunctionTool.from_defaults(
            fn=get_schema,
            name="get_project_schema",
            description=(
                "Returns the IFC schema context for the current branch: unique IFC "
                "classes present, their common attribute keys, available filter "
                "operators (string, numeric, class), IFC class hierarchy, and "
                "relationship types. Also returns valid attribute value types "
                "(string, numeric, object) and hints (e.g. PropertySets => object). "
                "Call this FIRST to understand what data exists before creating "
                "any filters. No arguments required."
            ),
        ),
        FunctionTool.from_defaults(
            fn=create_fs,
            name="create_filter_set",
            description=(
                "Creates a new empty named filter set on the current branch. Returns "
                "the filter_set_id for subsequent add_filter_condition calls. The "
                "intra-set logic (AND/OR) controls how conditions within the set "
                "are combined. Parameters: name (required), logic (optional, AND/OR)."
            ),
        ),
        FunctionTool.from_defaults(
            fn=add_filter_condition,
            name="add_filter_condition",
            description=(
                "Appends a filter condition to an existing filter set. Each "
                "condition targets a mode (class, attribute, or relation) with "
                "a specific operator and value. Call repeatedly to add multiple "
                "conditions. Class mode operators: is, is_not, inherits_from. "
                "Attribute string operators: is, is_not, contains, not_contains, "
                "starts_with, ends_with, is_empty, is_not_empty. Attribute numeric "
                "operators: equals, not_equals, gt, lt, gte, lte. "
                "Attribute value_type must be one of string, numeric, object. "
                "Use object for nested object-key matching such as "
                "attribute=PropertySets with value=Pset_WallCommon."
            ),
        ),
        FunctionTool.from_defaults(
            fn=apply_fs,
            name="apply_filter_set_to_context",
            description=(
                "Applies one or more filter sets to the current branch, updating "
                "the active view. This replaces any previously applied filter sets. "
                "After application, the frontend view refreshes to show only "
                "matching entities. Returns the count of matched entities. "
                "Parameters: filter_set_ids (list of UUIDs), combination_logic (OR)."
            ),
        ),
    ]
