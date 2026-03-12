"""Filter logic tree canonicalization and validation.

Supports nested Match ALL / Match ANY trees (max depth 2) stored in JSONB.
Provides:
- canonicalize_filters(): Convert legacy flat array to tree or ensure tree shape
- is_legacy_filters(): Detect legacy flat payload
- validate_filter_tree(): Enforce max depth and schema (used by API + DB layer)
"""

from __future__ import annotations

from typing import Any


MAX_DEPTH = 2
VALID_OPS = frozenset({"ALL", "ANY"})
LEGACY_LOGIC_MAP = {"AND": "ALL", "OR": "ANY"}


def is_legacy_filters(filters: Any) -> bool:
    """Return True if filters is a legacy flat array of leaf conditions."""
    return isinstance(filters, list) and (
        len(filters) == 0
        or not isinstance(filters[0], dict)
        or filters[0].get("kind") != "group"
    )


def _ensure_leaf(f: dict) -> dict:
    """Ensure a leaf dict has kind='leaf' for canonical shape."""
    out = dict(f)
    if out.get("kind") != "leaf":
        out["kind"] = "leaf"
    return out


def canonicalize_filters(
    filters: Any,
    logic: str | None = "AND",
) -> dict:
    """Convert filters to canonical tree shape.

    - If filters is a legacy flat array, wrap in root group.
    - If filters is already a tree, return as-is (assumed valid).
    - logic: "AND" | "OR" used when wrapping legacy array.
    """
    if not is_legacy_filters(filters):
        if isinstance(filters, dict) and filters.get("kind") == "group":
            return filters
        # Malformed: treat as empty
        return {"kind": "group", "op": "ALL", "children": []}

    flat = filters if isinstance(filters, list) else []
    op = LEGACY_LOGIC_MAP.get((logic or "AND").upper(), "ALL")
    children = [_ensure_leaf(f) for f in flat if isinstance(f, dict) and f.get("mode")]
    return {"kind": "group", "op": op, "children": children}


def _validate_node(node: Any, depth: int, path: str) -> list[str]:
    """Recursively validate tree node. Returns list of error messages."""
    errors: list[str] = []

    if depth > MAX_DEPTH:
        errors.append(f"{path}: max depth {MAX_DEPTH} exceeded (got {depth})")
        return errors

    if not isinstance(node, dict):
        errors.append(f"{path}: expected object, got {type(node).__name__}")
        return errors

    kind = node.get("kind")
    if kind == "leaf":
        mode = node.get("mode") or "class"
        if mode not in ("class", "attribute", "relation"):
            errors.append(f"{path}: invalid mode '{mode}'")
        return errors

    if kind == "group":
        op = node.get("op")
        if op not in VALID_OPS:
            errors.append(f"{path}: op must be ALL or ANY, got {op!r}")
        children = node.get("children")
        if not isinstance(children, list):
            errors.append(f"{path}: children must be array")
            return errors
        # Root group may be empty (create_filter_set before add_filter_condition).
        # Nested subgroups must have at least one child.
        if len(children) == 0 and path != "root":
            errors.append(f"{path}: group must have at least one child")
        for i, child in enumerate(children):
            child_path = f"{path}.children[{i}]"
            if isinstance(child, dict) and child.get("kind") == "group":
                errors.extend(_validate_node(child, depth + 1, child_path))
            else:
                errors.extend(_validate_node(child, depth + 1, child_path))
        return errors

    errors.append(f"{path}: kind must be 'group' or 'leaf', got {kind!r}")
    return errors


def validate_filter_tree(tree: Any) -> list[str]:
    """Validate canonical filter tree. Returns list of error messages (empty if valid)."""
    if not isinstance(tree, dict):
        return ["root: expected object"]
    if tree.get("kind") != "group":
        return ["root: must be a group node"]
    return _validate_node(tree, 0, "root")


def flatten_tree_to_filters(tree: dict) -> list[dict]:
    """Flatten tree to legacy list of leaf dicts (depth-first) for backward compat output."""
    out: list[dict] = []

    def visit(node: Any) -> None:
        if not isinstance(node, dict):
            return
        if node.get("kind") == "leaf":
            leaf = dict(node)
            leaf.pop("kind", None)
            out.append(leaf)
        elif node.get("kind") == "group":
            for c in node.get("children", []):
                visit(c)

    visit(tree)
    return out
