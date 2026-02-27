"""Utilities for working with the IFC4x3 schema metadata.

Historically this module loaded ``apps/api/schema/ifc_4_3_schema.json`` from
disk. That JSON is now treated purely as a **seed artifact**: it can be
uploaded once via an API endpoint to populate ``ifc_schema`` +
``validation_rule`` rows.

At runtime this module reads the schema definition from the database so that:

- The API does not depend on local JSON files being present.
- Multiple schema versions can be registered by name.
- Validation logic (inheritance, abstract flags, attributes) is centralised in
  normalized ``validation_rule`` rows linked to ``ifc_schema``.

The stored JSON shape matches the generator output from
``apps/api/scripts/generate_ifc_4_3_schema.py``::

    {
      "schema": "IFC4X3_ADD2",
      "entities": {
        "IfcWall": {
          "abstract": false,
          "parent": "IfcBuildingElement",
          "attributes": [
            {"name": "GlobalId", "type": "IfcGloballyUniqueId", "required": true},
            ...
          ]
        },
        ...
      }
    }

This module exposes helpers to:

- Look up a single entity definition by name.
- Resolve all *concrete* descendants of a given entity.
- Resolve the full ordered attribute chain for an entity by walking the
  inheritance hierarchy from root -> leaf.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional, Set

from ..db import fetch_validation_rules


# Default IFC schema identifier used by the generator and IfcOpenShell.
DEFAULT_SCHEMA_NAME = "IFC4X3_ADD2"


@lru_cache(maxsize=1)
def _load_schema() -> Dict[str, Any]:
    """Load and cache the full IFC4x3 schema JSON from the DB.

    The underlying data comes from ``ifc_schema`` + ``validation_rule``, keyed by
    ``schema_name`` (see :data:`DEFAULT_SCHEMA_NAME`). The JSON is expected to
    match the generator output shape documented in this module docstring.
    """
    data = fetch_validation_rules(DEFAULT_SCHEMA_NAME)
    if data is None:
        raise RuntimeError(
            f"No validation rules found for schema '{DEFAULT_SCHEMA_NAME}'. "
            "Upload an IFC schema JSON via the /ifc-schema endpoint first."
        )

    # Normalise to just the entities map for convenience.
    entities = data.get("entities") or {}
    if not isinstance(entities, dict):
        raise ValueError("Invalid IFC4x3 schema JSON: 'entities' must be a dict")
    return entities


@lru_cache(maxsize=1)
def _children_index() -> Dict[Optional[str], List[str]]:
    """Build and cache a parent -> children adjacency map for all entities."""
    entities = _load_schema()
    children: Dict[Optional[str], List[str]] = {}
    for cls_name, meta in entities.items():
        parent = meta.get("parent")
        children.setdefault(parent, []).append(cls_name)
    return children


def get_entity(name: str) -> Optional[Dict[str, Any]]:
    """Return the raw entity dict for an IFC class name, or None if unknown."""
    entities = _load_schema()
    return entities.get(name)


def get_parent(name: str) -> Optional[str]:
    """Return the direct parent (supertype) name for an entity, if any."""
    ent = get_entity(name)
    if not ent:
        return None
    parent = ent.get("parent")
    return parent or None


def get_full_attribute_chain(name: str) -> List[Dict[str, Any]]:
    """Return the ordered full attribute list for an entity.

    Attributes are resolved by walking the inheritance chain from the root
    ancestor down to the requested entity, concatenating each level's
    declared attributes in order. This preserves the overall attribute
    order defined by the schema.
    """
    entities = _load_schema()
    if name not in entities:
        return []

    chain: List[str] = []
    current: Optional[str] = name
    while current is not None:
        chain.append(current)
        current = get_parent(current)

    # Walk from root -> leaf by reversing the collected chain.
    attrs: List[Dict[str, Any]] = []
    for cls_name in reversed(chain):
        ent = entities.get(cls_name) or {}
        level_attrs = ent.get("attributes") or []
        if isinstance(level_attrs, list):
            attrs.extend(level_attrs)
    return attrs


def get_children(name: str) -> List[str]:
    """Return the direct child classes for an entity name."""
    return list(_children_index().get(name, []))


def get_descendants(name: str, include_self: bool = False, concrete_only: bool = True) -> List[str]:
    """Return a sorted list of descendant class names for an entity.

    Parameters
    ----------
    name:
        The IFC entity name to start from, e.g. ``"IfcProduct"``.
    include_self:
        If True, include ``name`` in the returned list.
    concrete_only:
        If True, skip abstract entities in the output.
    """
    entities = _load_schema()
    if name not in entities:
        return []

    children = _children_index()

    result: Set[str] = set()
    to_visit: List[str] = list(children.get(name, []))

    while to_visit:
        cls = to_visit.pop()
        ent = entities.get(cls) or {}
        is_abstract = bool(ent.get("abstract"))
        if not (concrete_only and is_abstract):
            result.add(cls)
        # Enqueue children of this class.
        for child in children.get(cls, []):
            to_visit.append(child)

    if include_self:
        ent = entities.get(name) or {}
        if not (concrete_only and bool(ent.get("abstract"))):
            result.add(name)

    return sorted(result)


def iter_entities() -> Iterable[str]:
    """Yield all entity names known to the loaded schema."""
    return _load_schema().keys()

