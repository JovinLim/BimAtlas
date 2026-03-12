"""MCP tool implementations for the Agentic Filtering Framework.

Each tool wraps existing DB functions and exposes them as callable functions
that LlamaIndex can bind as ``FunctionTool`` instances.  The tools operate
within a *context* (branch_id + optional revision) injected at agent
instantiation time.

Filter tree model
-----------------
Filters are stored as a tree (max depth 2):
- Root (depth 0): single group with op ALL (Match ALL) or ANY (Match ANY).
- Sub-groups (depth 1): optional nested groups, each with its own op.
- Leaves (depth 1 or 2): individual conditions (class, attribute, relation).

Example: "Walls AND (Name contains Core OR Tag is A1)" =>
  Root(ALL) [leaf: IfcWall, group(ANY) [leaf: Name contains Core, leaf: Tag is A1]]

Tools
-----
1. get_project_schema  – discover IFC classes, attributes, operators
2. create_filter_set   – create a named empty filter set
3. add_filter_condition – append a condition (optionally to a nested group)
4. add_filter_group    – create a nested group with its first condition
5. apply_filter_set_to_context – apply filter sets to a branch view
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


def _coerce_filter_tree(filters_raw: Any, logic: str | None) -> dict[str, Any]:
    """Normalize legacy or canonical filter payloads to a canonical tree."""
    from src.schema.filter_tree import canonicalize_filters, is_legacy_filters

    if isinstance(filters_raw, str):
        filters_raw = json.loads(filters_raw)
    tree = (
        canonicalize_filters(filters_raw, logic)
        if is_legacy_filters(filters_raw)
        else filters_raw
    )
    if not isinstance(tree, dict) or tree.get("kind") != "group":
        tree = canonicalize_filters([], logic)
    return tree


def _flatten_filter_tree(tree: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten a canonical tree for legacy callers."""
    from src.schema.filter_tree import flatten_tree_to_filters

    return flatten_tree_to_filters(tree) if isinstance(tree, dict) else []


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


def _get_parent_children(tree: dict[str, Any], parent_path: str | None) -> list:
    """Return the children list for the given path.

    parent_path: 'root' (default) or integer index of a root child that is a group.
    """
    children = tree.setdefault("children", [])
    if parent_path in ("root", "", None):
        return children
    try:
        idx = int(parent_path)
    except (ValueError, TypeError):
        raise ValueError(
            f"Invalid parent_path: {parent_path!r}. Use 'root' or integer index of a group."
        )
    if idx < 0 or idx >= len(children):
        raise ValueError(
            f"Invalid parent_path: {parent_path}. No child at index {idx}. "
            "Use add_filter_group first to create a nested group."
        )
    parent = children[idx]
    if not isinstance(parent, dict) or parent.get("kind") != "group":
        raise ValueError(
            f"Child at index {idx} is not a group. Use add_filter_group first."
        )
    return parent.setdefault("children", [])


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
    """Create a new empty named filter set on a branch. Returns the filter set
    ID for subsequent add_filter_condition and add_filter_group calls.

    The filter tree has a root group (depth 0) with op ALL or ANY. Conditions
    and nested groups are added as children. Max depth is 2.

    Parameters
    ----------
    branch_id : UUID string of the target branch.
    name : Human-readable name (e.g. 'Fire-rated walls').
    logic : Root group op — 'AND' (Match ALL) or 'OR' (Match ANY).
    """
    _validate_uuid(branch_id, "branch_id")
    if logic not in ("AND", "OR"):
        logic = "AND"

    row = db_create_filter_set(branch_id, name, logic, filters_json=[])
    event_bus.publish_filter_set_changed(branch_id)
    tree = _coerce_filter_tree(row.get("filters") or [], row.get("logic"))
    return {
        "filter_set_id": row["filter_set_id"],
        "name": row["name"],
        "logic": row["logic"],
        "filters": [],
        "filters_tree": tree,
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
    parent_path: Optional[str] = "root",
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
    parent_path : 'root' (default) to add to root, or integer index of a nested
        group (from add_filter_group result) to add inside that group. Max depth 2.
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

    tree = _coerce_filter_tree(existing.get("filters") or [], existing.get("logic"))

    normalized_value_type: str | None = None
    if mode == "attribute":
        normalized_value_type = _normalize_value_type(value_type, attribute, operator)

    new_condition: dict[str, Any] = {"kind": "leaf", "mode": mode, "operator": operator}
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

    children = _get_parent_children(tree, parent_path)
    children.append(new_condition)
    updated = db_update_filter_set(filter_set_id, filters_json=tree)
    if updated is None:
        raise ValueError(f"Failed to update filter set {filter_set_id}.")

    branch_id = existing.get("branch_id") or existing.get("branchId")
    if branch_id:
        event_bus.publish_filter_set_changed(str(branch_id))

    filters_tree = _coerce_filter_tree(updated.get("filters") or {}, updated.get("logic"))
    flat = _flatten_filter_tree(filters_tree)

    return {
        "filter_set_id": updated["filter_set_id"],
        "name": updated["name"],
        "logic": updated["logic"],
        "filters": flat,
        "filters_tree": filters_tree,
        "condition_count": len(flat),
    }


# ---------------------------------------------------------------------------
# Tool 4: add_filter_group
# ---------------------------------------------------------------------------

def add_filter_group(
    filter_set_id: str,
    op: str,
    mode: str,
    operator: str,
    ifc_class: Optional[str] = None,
    attribute: Optional[str] = None,
    value: Optional[str] = None,
    value_type: Optional[str] = None,
    relation: Optional[str] = None,
    parent_path: Optional[str] = "root",
) -> dict[str, Any]:
    """Create a nested group with its first condition. Use for mixed logic like
    "A AND (B OR C)": create root with logic=AND, add A to root, add_group with
    op=OR and first condition B, then add_filter_condition with parent_path=group_index
    to add C.

    Parameters
    ----------
    filter_set_id : UUID of the filter set to modify.
    op : 'AND' or 'OR' — how conditions inside this group are combined.
    mode, operator, ifc_class, attribute, value, value_type, relation : Same as
        add_filter_condition (the first condition for this group).
    parent_path : 'root' (default) to add group under root. Max depth is 2, so
        groups can only be direct children of root.
    """
    _validate_uuid(filter_set_id, "filter_set_id")
    op_upper = (op or "AND").upper()
    if op_upper not in ("AND", "OR"):
        op_upper = "AND"

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

    tree = _coerce_filter_tree(existing.get("filters") or [], existing.get("logic"))

    normalized_value_type: str | None = None
    if mode == "attribute":
        normalized_value_type = _normalize_value_type(value_type, attribute, operator)

    first_leaf: dict[str, Any] = {"kind": "leaf", "mode": mode, "operator": operator}
    if ifc_class:
        first_leaf["ifcClass"] = ifc_class
    if attribute:
        first_leaf["attribute"] = attribute
    if value is not None:
        first_leaf["value"] = value
    if normalized_value_type:
        first_leaf["valueType"] = normalized_value_type
    if relation:
        first_leaf["relation"] = relation

    group_op = "ALL" if op_upper == "AND" else "ANY"
    new_group: dict[str, Any] = {
        "kind": "group",
        "op": group_op,
        "children": [first_leaf],
    }

    parent_children = _get_parent_children(tree, parent_path)
    group_index = len(parent_children)
    parent_children.append(new_group)

    updated = db_update_filter_set(filter_set_id, filters_json=tree)
    if updated is None:
        raise ValueError(f"Failed to update filter set {filter_set_id}.")

    branch_id = existing.get("branch_id") or existing.get("branchId")
    if branch_id:
        event_bus.publish_filter_set_changed(str(branch_id))

    filters_tree = _coerce_filter_tree(updated.get("filters") or {}, updated.get("logic"))
    flat = _flatten_filter_tree(filters_tree)

    return {
        "filter_set_id": updated["filter_set_id"],
        "name": updated["name"],
        "logic": updated["logic"],
        "group_index": group_index,
        "filters": flat,
        "filters_tree": filters_tree,
        "condition_count": len(flat),
    }


# ---------------------------------------------------------------------------
# Tool 5: apply_filter_set_to_context
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
            filters_tree = _coerce_filter_tree(fs.get("filters") or [], fs.get("logic"))
            applied_summary.append({
                "id": fs["filter_set_id"],
                "name": fs["name"],
                "condition_count": len(_flatten_filter_tree(filters_tree)),
                "filters_tree": filters_tree,
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
                "filter_set_id for subsequent add_filter_condition and add_filter_group. "
                "Filter tree model: root group (depth 0) with op ALL or ANY; optional "
                "sub-groups (depth 1) with their own op; leaves at depth 1 or 2. "
                "The logic parameter sets the root's op: AND=Match ALL, OR=Match ANY. "
                "Parameters: name (required), logic (optional, AND/OR). "
                "Limitation: max depth 2 — groups can only be direct children of root."
            ),
        ),
        FunctionTool.from_defaults(
            fn=add_filter_condition,
            name="add_filter_condition",
            description=(
                "Appends a filter condition (leaf) to an existing filter set. Use "
                "parent_path='root' (default) to add to root, or parent_path=<group_index> "
                "to add inside a nested group (group_index from add_filter_group result). "
                "Modes: class (ifc_class required), attribute (attribute, value, value_type), "
                "relation (relation required). Operators: class: is, is_not, inherits_from; "
                "attribute string: is, is_not, contains, not_contains, starts_with, ends_with, "
                "is_empty, is_not_empty; attribute numeric: equals, not_equals, gt, lt, gte, lte. "
                "value_type: string, numeric, or object (use object for PropertySets key matching)."
            ),
        ),
        FunctionTool.from_defaults(
            fn=add_filter_group,
            name="add_filter_group",
            description=(
                "Creates a nested group with its first condition. Use for mixed logic like "
                "'A AND (B OR C)': create_filter_set(logic=AND), add_filter_condition(A), "
                "add_filter_group(op=OR, first condition B) → returns group_index, then "
                "add_filter_condition(C, parent_path=group_index). op: AND or OR for "
                "how conditions inside the group combine. Same mode/operator/params as "
                "add_filter_condition for the first condition. Returns group_index for "
                "subsequent add_filter_condition(parent_path=group_index). "
                "Limitation: groups can only be children of root (max depth 2)."
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
                "Parameters: filter_set_ids (list of UUIDs), combination_logic (OR). "
                "Limitation: combination_logic between multiple sets is always OR."
            ),
        ),
    ]
