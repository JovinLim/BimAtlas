"""
Generate a compact IFC4x3 schema JSON for BimAtlas.

The output shape matches the plan in `.cursor/plans/ifc_4.3_schema_+_db_tree_dc76bb2f.plan.md`:

{
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

Only *direct* (declared) attributes are stored per-entity. A consumer that
needs the full attribute chain for a child class can walk up ``parent``
links and concatenate attributes in order.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import ifcopenshell


# IFC schema identifier used by the installed IfcOpenShell build.
# IFC4X3_ADD2 is the common identifier for the final IFC 4.3 release.
IFC_SCHEMA_NAME = "IFC4X3_ADD2"


def _get_schema() -> Any:
    """Return the IFC schema definition for IFC4x3.

    Falls back to a generic "IFC4X3" identifier if the ADD2 one is not
    available, so the script remains usable across different builds.
    """
    try:
        return ifcopenshell.schema_by_name(IFC_SCHEMA_NAME)
    except Exception:
        # Fallback for builds that expose the schema under a slightly
        # different identifier (e.g. IFC4X3, IFC4X3_RC4, etc.).
        # This intentionally keeps the logic simple – if this also fails,
        # the caller will see a clear exception.
        return ifcopenshell.schema_by_name("IFC4X3")


def _resolve_parent_name(entity_decl: Any) -> Optional[str]:
    """Return the direct supertype name for an entity or None."""
    parent = entity_decl.supertype()
    if parent is None:
        return None
    # ``supertype()`` returns an `entity` declaration; `.name()` gives the
    # IFC entity name such as "IfcProduct".
    return parent.name()


def _attribute_type_string(attr: Any) -> str:
    """Best-effort string representation of an IFC attribute type.

    This uses the low-level `parameter_type` helpers exposed by IfcOpenShell.
    The goal here is to capture *readable* type information, not to be a
    full EXPRESS pretty-printer, so the logic intentionally stays simple.
    """
    try:
        ptype = attr.type_of_attribute()
    except Exception:
        return "UNKNOWN"

    # Aggregates (LIST, SET, ARRAY, BAG OF T)
    agg = getattr(ptype, "as_aggregation_type", lambda: None)()
    if agg is not None:
        kind = getattr(agg, "type_of_aggregation_string", lambda: None)()
        if not kind:
            kind = "AGGREGATE"
        elem_type = getattr(agg, "type_of_element", lambda: None)()
        base = "UNKNOWN"
        if elem_type is not None:
            # Try named type first (e.g. IfcLabel, IfcWall, ...)
            named = getattr(elem_type, "as_named_type", lambda: None)()
            if named is not None:
                try:
                    base = named.declared_type().name()
                except Exception:
                    base = "UNKNOWN"
            else:
                simple = getattr(elem_type, "as_simple_type", lambda: None)()
                if simple is not None:
                    try:
                        # Simple types do not always expose a declared_type
                        # so fall back to their Python `repr`.
                        base = str(simple)
                    except Exception:
                        base = "SIMPLE"
        return f"{kind} OF {base}"

    # Named / simple scalar types
    named = getattr(ptype, "as_named_type", lambda: None)()
    if named is not None:
        try:
            return named.declared_type().name()
        except Exception:
            return "UNKNOWN"

    simple = getattr(ptype, "as_simple_type", lambda: None)()
    if simple is not None:
        try:
            return str(simple)
        except Exception:
            return "SIMPLE"

    return "UNKNOWN"


def _entity_to_dict(entity_decl: Any) -> Dict[str, Any]:
    """Convert an IfcOpenShell entity declaration into our JSON shape."""
    name = entity_decl.name()
    is_abstract = bool(entity_decl.is_abstract())
    parent_name = _resolve_parent_name(entity_decl)

    # `attributes()` returns only the direct attributes declared on this
    # entity in schema order, which is exactly what we want here.
    attributes_out: List[Dict[str, Any]] = []
    for attr in entity_decl.attributes():
        attr_name = attr.name()
        # Required iff the EXPRESS attribute is not marked OPTIONAL.
        try:
            required = not bool(attr.optional())
        except Exception:
            required = True

        type_str = _attribute_type_string(attr)
        attributes_out.append(
            {
                "name": attr_name,
                "type": type_str,
                "required": required,
            }
        )

    return {
        "name": name,
        "abstract": is_abstract,
        "parent": parent_name,
        "attributes": attributes_out,
    }


def build_ifc4x3_schema() -> Dict[str, Any]:
    """Build the full IFC4x3 entity map as a Python dict."""
    schema = _get_schema()

    entities: Dict[str, Dict[str, Any]] = {}
    for decl in schema.declarations():
        # Filter to entity declarations only – skip types, selects, etc.
        # `as_entity()` returns None for non-entity declarations.
        if getattr(decl, "as_entity", None) is None:
            continue
        entity_decl = decl.as_entity()
        if entity_decl is None:
            continue

        entity_dict = _entity_to_dict(entity_decl)
        entities[entity_dict["name"]] = {
            "abstract": entity_dict["abstract"],
            "parent": entity_dict["parent"],
            "attributes": entity_dict["attributes"],
        }

    return {"schema": IFC_SCHEMA_NAME, "entities": entities}


def main() -> None:
    """Entry point for CLI usage."""
    # Script lives at apps/api/scripts/, so the repo root is three levels up.
    project_root = Path(__file__).resolve().parents[3]
    output_dir = project_root / "apps" / "api" / "schema"
    output_path = output_dir / "ifc_4_3_schema.json"

    output_dir.mkdir(parents=True, exist_ok=True)

    schema_dict = build_ifc4x3_schema()
    # Use a stable, compact but readable JSON encoding.
    output_path.write_text(
        json.dumps(schema_dict, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(f"Wrote IFC4x3 schema for {schema_dict['schema']} to {output_path}")


if __name__ == "__main__":
    main()

