"""AGE Cypher query builder/executor.

Graph nodes are labeled by IFC class; edges by IFC relationship name.
All carry ``valid_from_rev`` / ``valid_to_rev`` for versioning (``-1`` means
current, since AGE does not support NULL properties).

Executes Cypher through AGE's SQL interface
(``SELECT * FROM cypher(…)``) using the psycopg2 connection pool from
:mod:`src.db`.
"""

from __future__ import annotations

import json
import re
from typing import Any

from ...config import AGE_GRAPH
from ...db import get_conn, put_conn
from . import queries as cypher_tpl

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

# IFC GlobalIds are 22-char base64 (A-Za-z0-9_$). We also allow hyphens for
# safety.  The important thing is to reject characters that could break Cypher
# string literals (quotes, backslashes, braces, etc.).
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_$\-]+$")


def _validate_id(value: str) -> str:
    """Ensure *value* is safe to embed in a Cypher string literal."""
    if not value or not _SAFE_ID_RE.match(value):
        raise ValueError(f"Invalid identifier for Cypher embedding: {value!r}")
    return value


# ---------------------------------------------------------------------------
# Revision filter helper
# ---------------------------------------------------------------------------


def _rev_filter(alias: str, rev: int) -> str:
    """Generate a Cypher WHERE clause for revision-scoped visibility.

    AGE uses ``-1`` instead of NULL for open-ended ``valid_to_rev``.
    """
    r = int(rev)
    return (
        f"{alias}.valid_from_rev <= {r} "
        f"AND ({alias}.valid_to_rev = -1 OR {alias}.valid_to_rev > {r})"
    )


# ---------------------------------------------------------------------------
# Low-level Cypher execution
# ---------------------------------------------------------------------------


def _parse_agtype(val: Any) -> Any:
    """Deserialise a raw agtype value returned by psycopg2.

    psycopg2 returns AGE ``agtype`` columns as Python strings.  Scalar
    agtypes follow JSON encoding (strings are double-quoted, numbers are
    bare, etc.) so :func:`json.loads` handles the common cases.
    """
    if val is None:
        return None
    if isinstance(val, (int, float, bool)):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, ValueError):
            return val
    return val


def _exec_cypher(cypher: str, cols: list[str]) -> list[tuple]:
    """Execute a Cypher query via the AGE SQL interface and return parsed rows.

    Each returned row is a tuple of Python scalars (``str``, ``int``,
    ``None``, …) in the order of *cols*.

    The function obtains a connection from the pool, configures it for AGE,
    runs the query, and returns the connection.
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("LOAD 'age';")
            cur.execute('SET search_path = ag_catalog, "$user", public;')

            col_spec = ", ".join(f"{c} agtype" for c in cols)
            sql = (
                f"SELECT * FROM cypher('{AGE_GRAPH}', $$ {cypher} $$) "
                f"AS ({col_spec})"
            )
            cur.execute(sql)
            rows = cur.fetchall()
        conn.commit()
        return [tuple(_parse_agtype(v) for v in row) for row in rows]
    except Exception:
        conn.rollback()
        raise
    finally:
        put_conn(conn)


# ---------------------------------------------------------------------------
# Public query functions
# ---------------------------------------------------------------------------


def get_neighbors(global_id: str, rev: int) -> list[dict]:
    """Return outgoing **and** incoming neighbors of *global_id* at *rev*.

    Each dict has keys: ``global_id``, ``ifc_class``, ``name``,
    ``relationship`` (IFC relationship entity name, e.g.
    ``"IfcRelContainedInSpatialStructure"``).
    """
    gid = _validate_id(global_id)
    cols = ["gid", "lbl", "name", "rel"]
    results: list[dict] = []
    seen: set[tuple[str, str]] = set()  # (global_id, rel) for dedup

    for tpl in (cypher_tpl.NEIGHBORS_OUT, cypher_tpl.NEIGHBORS_IN):
        cypher = tpl.format(
            global_id=gid,
            n_filter=_rev_filter("n", rev),
            r_filter=_rev_filter("r", rev),
            m_filter=_rev_filter("m", rev),
        )
        for row in _exec_cypher(cypher, cols):
            key = (row[0], row[3])
            if key not in seen:
                seen.add(key)
                results.append(
                    {
                        "global_id": row[0],
                        "ifc_class": row[1],
                        "name": row[2],
                        "relationship": row[3],
                    }
                )

    return results


def get_spatial_tree_roots(rev: int) -> list[dict]:
    """Return ``IfcProject`` root nodes visible at *rev*."""
    cypher = cypher_tpl.SPATIAL_ROOTS.format(p_filter=_rev_filter("p", rev))
    cols = ["gid", "lbl", "name"]
    return [
        {"global_id": r[0], "ifc_class": r[1], "name": r[2]}
        for r in _exec_cypher(cypher, cols)
    ]


def get_spatial_children(global_id: str, rev: int) -> list[dict]:
    """Return direct spatial children (via ``IfcRelAggregates``) of *global_id*."""
    gid = _validate_id(global_id)
    cypher = cypher_tpl.SPATIAL_CHILDREN.format(
        global_id=gid,
        parent_filter=_rev_filter("parent", rev),
        r_filter=_rev_filter("r", rev),
        child_filter=_rev_filter("child", rev),
    )
    cols = ["gid", "lbl", "name"]
    return [
        {"global_id": r[0], "ifc_class": r[1], "name": r[2]}
        for r in _exec_cypher(cypher, cols)
    ]


def get_contained_elements(spatial_global_id: str, rev: int) -> list[dict]:
    """Return elements contained in a spatial structure node at *rev*."""
    gid = _validate_id(spatial_global_id)
    cypher = cypher_tpl.CONTAINED_ELEMENTS.format(
        global_id=gid,
        spatial_filter=_rev_filter("spatial", rev),
        r_filter=_rev_filter("r", rev),
        elem_filter=_rev_filter("elem", rev),
    )
    cols = ["gid", "lbl", "name"]
    return [
        {"global_id": r[0], "ifc_class": r[1], "name": r[2]}
        for r in _exec_cypher(cypher, cols)
    ]


# ---------------------------------------------------------------------------
# Spatial tree builder (recursive)
# ---------------------------------------------------------------------------


def build_spatial_tree(rev: int) -> list[dict]:
    """Build the full spatial decomposition tree at *rev*.

    Returns a list of root nodes (``IfcProject``), each with recursive
    ``children`` (via ``IfcRelAggregates``) and ``contained_elements``
    (via ``IfcRelContainedInSpatialStructure``) lists.

    The spatial tree is typically small (Project > Site > Building > Storey >
    Space) so the recursive query pattern is acceptable.
    """
    roots = get_spatial_tree_roots(rev)
    return [_build_subtree(node, rev) for node in roots]


def _build_subtree(node: dict, rev: int) -> dict:
    """Recursively expand a spatial node into a tree dict."""
    children_data = get_spatial_children(node["global_id"], rev)
    contained = get_contained_elements(node["global_id"], rev)
    return {
        "global_id": node["global_id"],
        "ifc_class": node["ifc_class"],
        "name": node.get("name"),
        "children": [_build_subtree(c, rev) for c in children_data],
        "contained_elements": contained,
    }
