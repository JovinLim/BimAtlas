"""AGE Cypher query builder/executor.

Graph nodes are labeled by IFC class; edges by IFC relationship name.
All carry ``valid_from_rev`` / ``valid_to_rev`` for versioning (``-1`` means
current, since AGE does not support NULL properties) and ``branch_id`` for
branch scoping.

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

# AGE labels (node/edge) must be valid identifiers.
_SAFE_LABEL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_id(value: str) -> str:
    """Ensure *value* is safe to embed in a Cypher string literal."""
    if not value or not _SAFE_ID_RE.match(value):
        raise ValueError(f"Invalid identifier for Cypher embedding: {value!r}")
    return value


def _validate_label(label: str) -> str:
    """Ensure *label* is a valid AGE vertex/edge label."""
    if not label or not _SAFE_LABEL_RE.match(label):
        raise ValueError(f"Invalid Cypher label: {label!r}")
    return label


def _escape_cypher_string(value: str | None) -> str:
    """Escape a string for safe embedding inside a Cypher single-quoted literal."""
    if value is None:
        return ""
    return value.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")


# ---------------------------------------------------------------------------
# Revision filter helper
# ---------------------------------------------------------------------------


def _rev_filter(alias: str, rev: int, branch_id: str) -> str:
    """Generate a Cypher WHERE clause for revision-scoped, branch-scoped visibility.

    AGE uses ``-1`` instead of NULL for open-ended ``valid_to_rev``.  The *rev*
    parameter is the integer ``revision_seq``; *branch_id* is stored as a UUID
    string property on nodes and edges.
    """
    r = int(rev)
    b = _escape_cypher_string(str(branch_id))
    return (
        f"{alias}.branch_id = '{b}' "
        f"AND {alias}.valid_from_rev <= {r} "
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
                f"SELECT * FROM cypher('{AGE_GRAPH}', $CYPHER$ {cypher} $CYPHER$) "
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
# Write execution
# ---------------------------------------------------------------------------


def _exec_cypher_write(cypher: str) -> None:
    """Execute a Cypher write operation (CREATE, SET, DELETE).

    All write Cypher statements **must** include a ``RETURN`` clause so that the
    AGE ``AS (v agtype)`` column spec is satisfied.  Queries that match nothing
    simply return 0 rows.
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("LOAD 'age';")
            cur.execute('SET search_path = ag_catalog, "$user", public;')
            sql = (
                f"SELECT * FROM cypher('{AGE_GRAPH}', $CYPHER$ {cypher} $CYPHER$) "
                f"AS (v agtype)"
            )
            cur.execute(sql)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        put_conn(conn)


# ---------------------------------------------------------------------------
# Label management (AGE requires labels to exist before use)
# ---------------------------------------------------------------------------

_known_vlabels: set[str] = set()
_known_elabels: set[str] = set()


def _ensure_vlabel(label: str) -> None:
    """Create a vertex label in the graph if it does not already exist."""
    if label in _known_vlabels:
        return
    _validate_label(label)
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("LOAD 'age';")
            cur.execute('SET search_path = ag_catalog, "$user", public;')
            cur.execute(
                "SELECT 1 FROM ag_catalog.ag_label "
                "WHERE name = %s "
                "  AND graph = (SELECT graphid FROM ag_catalog.ag_graph WHERE name = %s) "
                "  AND kind = 'v'",
                (label, AGE_GRAPH),
            )
            if not cur.fetchone():
                cur.execute("SELECT create_vlabel(%s, %s)", (AGE_GRAPH, label))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        put_conn(conn)
    _known_vlabels.add(label)


def _ensure_elabel(label: str) -> None:
    """Create an edge label in the graph if it does not already exist."""
    if label in _known_elabels:
        return
    _validate_label(label)
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("LOAD 'age';")
            cur.execute('SET search_path = ag_catalog, "$user", public;')
            cur.execute(
                "SELECT 1 FROM ag_catalog.ag_label "
                "WHERE name = %s "
                "  AND graph = (SELECT graphid FROM ag_catalog.ag_graph WHERE name = %s) "
                "  AND kind = 'e'",
                (label, AGE_GRAPH),
            )
            if not cur.fetchone():
                cur.execute("SELECT create_elabel(%s, %s)", (AGE_GRAPH, label))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        put_conn(conn)
    _known_elabels.add(label)


# ---------------------------------------------------------------------------
# Graph write operations (revision-tagged, branch-scoped)
# ---------------------------------------------------------------------------


def create_node(
    ifc_class: str,
    global_id: str,
    name: str | None,
    rev_id: int,
    branch_id: str,
) -> None:
    """Create a revision-tagged, branch-scoped graph node labeled by its IFC class.

    The node carries ``branch_id``, ``valid_from_rev = rev_id`` and
    ``valid_to_rev = -1`` (current).
    """
    _ensure_vlabel(ifc_class)
    gid = _validate_id(global_id)
    safe_name = _escape_cypher_string(name)
    r = int(rev_id)
    b = _escape_cypher_string(str(branch_id))
    cypher = (
        f"CREATE (n:{ifc_class} {{"
        f"ifc_global_id: '{gid}', "
        f"name: '{safe_name}', "
        f"branch_id: '{b}', "
        f"valid_from_rev: {r}, "
        f"valid_to_rev: -1"
        f"}}) RETURN id(n)"
    )
    _exec_cypher_write(cypher)


def close_node(global_id: str, rev_id: int, branch_id: str) -> None:
    """Close a graph node by setting ``valid_to_rev``.

    Matches the **current** version of the node on the specified branch
    (``valid_to_rev = -1``) and marks it as superseded at *rev_id*.
    """
    gid = _validate_id(global_id)
    r = int(rev_id)
    b = _escape_cypher_string(str(branch_id))
    cypher = (
        f"MATCH (n {{ifc_global_id: '{gid}', branch_id: '{b}', valid_to_rev: -1}}) "
        f"SET n.valid_to_rev = {r} "
        f"RETURN id(n)"
    )
    _exec_cypher_write(cypher)


def create_edge(
    from_gid: str,
    to_gid: str,
    rel_type: str,
    rev_id: int,
    branch_id: str,
) -> None:
    """Create a revision-tagged, branch-scoped edge between two **current** nodes.

    Both endpoints must have ``valid_to_rev = -1`` and matching ``branch_id``.
    """
    _ensure_elabel(rel_type)
    f_gid = _validate_id(from_gid)
    t_gid = _validate_id(to_gid)
    r = int(rev_id)
    b = _escape_cypher_string(str(branch_id))
    cypher = (
        f"MATCH (a {{ifc_global_id: '{f_gid}', branch_id: '{b}', valid_to_rev: -1}}), "
        f"(b {{ifc_global_id: '{t_gid}', branch_id: '{b}', valid_to_rev: -1}}) "
        f"CREATE (a)-[r:{rel_type} {{branch_id: '{b}', valid_from_rev: {r}, valid_to_rev: -1}}]->(b) "
        f"RETURN id(r)"
    )
    _exec_cypher_write(cypher)


def close_edges_for_node(global_id: str, rev_id: int, branch_id: str) -> None:
    """Close all **current** edges (incoming and outgoing) for a node on a branch.

    Matches edges with ``valid_to_rev = -1`` and matching ``branch_id``
    connected to the node identified by *global_id*.
    """
    gid = _validate_id(global_id)
    r = int(rev_id)
    b = _escape_cypher_string(str(branch_id))
    # Close outgoing edges
    cypher_out = (
        f"MATCH ({{ifc_global_id: '{gid}', branch_id: '{b}'}})-[r {{branch_id: '{b}', valid_to_rev: -1}}]->() "
        f"SET r.valid_to_rev = {r} "
        f"RETURN id(r)"
    )
    _exec_cypher_write(cypher_out)
    # Close incoming edges
    cypher_in = (
        f"MATCH ({{ifc_global_id: '{gid}', branch_id: '{b}'}})<-[r {{branch_id: '{b}', valid_to_rev: -1}}]-() "
        f"SET r.valid_to_rev = {r} "
        f"RETURN id(r)"
    )
    _exec_cypher_write(cypher_in)


# ---------------------------------------------------------------------------
# Graph cleanup (branch/project deletion)
# ---------------------------------------------------------------------------


def delete_branch_graph_data(branch_id: str) -> None:
    """Delete all graph nodes and edges for the given branch.

    Used when deleting a branch or a project (called per branch). Uses
    DETACH DELETE so edges are removed with their nodes.
    """
    b = _escape_cypher_string(str(branch_id))
    cypher = f"MATCH (n {{branch_id: '{b}'}}) DETACH DELETE n RETURN true"
    _exec_cypher_write(cypher)


# ---------------------------------------------------------------------------
# Public query functions
# ---------------------------------------------------------------------------


def get_relations(global_id: str, rev: int, branch_id: str) -> list[dict]:
    """Return outgoing **and** incoming relations of *global_id* at *rev* on *branch_id*.

    Each dict has keys: ``global_id``, ``ifc_class``, ``name``,
    ``relationship`` (IFC relationship entity name).
    """
    gid = _validate_id(global_id)
    cols = ["gid", "lbl", "name", "rel"]
    results: list[dict] = []
    seen: set[tuple[str, str]] = set()  # (global_id, rel) for dedup

    for tpl in (cypher_tpl.NEIGHBORS_OUT, cypher_tpl.NEIGHBORS_IN):
        cypher = tpl.format(
            global_id=gid,
            n_filter=_rev_filter("n", rev, branch_id),
            r_filter=_rev_filter("r", rev, branch_id),
            m_filter=_rev_filter("m", rev, branch_id),
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


def get_product_ids_by_relation(
    rel_type: str, rev: int, branch_id: str,
) -> list[str]:
    """Return global_ids of all products participating in edges of *rel_type*."""
    label = _validate_label(rel_type)
    cypher = cypher_tpl.PRODUCTS_BY_RELATION.format(
        rel_type=label,
        r_filter=_rev_filter("r", rev, branch_id),
        n_filter=_rev_filter("n", rev, branch_id),
    )
    cols = ["gid"]
    return [row[0] for row in _exec_cypher(cypher, cols)]


def get_spatial_tree_roots(rev: int, branch_id: str) -> list[dict]:
    """Return ``IfcProject`` root nodes visible at *rev* on *branch_id*."""
    cypher = cypher_tpl.SPATIAL_ROOTS.format(p_filter=_rev_filter("p", rev, branch_id))
    cols = ["gid", "lbl", "name"]
    return [
        {"global_id": r[0], "ifc_class": r[1], "name": r[2]}
        for r in _exec_cypher(cypher, cols)
    ]


def get_spatial_children(global_id: str, rev: int, branch_id: str) -> list[dict]:
    """Return direct spatial children (via ``IfcRelAggregates``) of *global_id*."""
    gid = _validate_id(global_id)
    cypher = cypher_tpl.SPATIAL_CHILDREN.format(
        global_id=gid,
        parent_filter=_rev_filter("parent", rev, branch_id),
        r_filter=_rev_filter("r", rev, branch_id),
        child_filter=_rev_filter("child", rev, branch_id),
    )
    cols = ["gid", "lbl", "name"]
    return [
        {"global_id": r[0], "ifc_class": r[1], "name": r[2]}
        for r in _exec_cypher(cypher, cols)
    ]


def get_contained_elements(spatial_global_id: str, rev: int, branch_id: str) -> list[dict]:
    """Return elements contained in a spatial structure node at *rev* on *branch_id*."""
    gid = _validate_id(spatial_global_id)
    cypher = cypher_tpl.CONTAINED_ELEMENTS.format(
        global_id=gid,
        spatial_filter=_rev_filter("spatial", rev, branch_id),
        r_filter=_rev_filter("r", rev, branch_id),
        elem_filter=_rev_filter("elem", rev, branch_id),
    )
    cols = ["gid", "lbl", "name"]
    return [
        {"global_id": r[0], "ifc_class": r[1], "name": r[2]}
        for r in _exec_cypher(cypher, cols)
    ]


def get_element_relations(
    rel_types: list[str],
    rev: int,
    branch_id: str,
) -> list[dict]:
    """Return non-spatial element relations at *rev* on *branch_id*.

    Each dict has keys:
      - ``source_id``, ``source_class``, ``source_name``
      - ``target_id``, ``target_class``, ``target_name``
      - ``relationship`` (edge label)
    """
    if not rel_types:
        return []

    labels = [_validate_label(rt) for rt in rel_types]
    rel_list = ", ".join(f"'{lbl}'" for lbl in labels)

    cypher = cypher_tpl.ELEMENT_RELATIONS.format(
        a_filter=_rev_filter("a", rev, branch_id),
        r_filter=_rev_filter("r", rev, branch_id),
        b_filter=_rev_filter("b", rev, branch_id),
        rel_type_filter=f"type(r) IN [{rel_list}]",
    )
    cols = ["src", "src_lbl", "src_name", "dst", "dst_lbl", "dst_name", "rel"]
    rows = _exec_cypher(cypher, cols)
    return [
        {
            "source_id": r[0],
            "source_class": r[1],
            "source_name": r[2],
            "target_id": r[3],
            "target_class": r[4],
            "target_name": r[5],
            "relationship": r[6],
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Spatial tree builder (recursive)
# ---------------------------------------------------------------------------


def build_spatial_tree(rev: int, branch_id: str) -> list[dict]:
    """Build the full spatial decomposition tree at *rev* on *branch_id*.

    Returns a list of root nodes (``IfcProject``), each with recursive
    ``children`` and ``contained_elements`` lists.
    """
    roots = get_spatial_tree_roots(rev, branch_id)
    return [_build_subtree(node, rev, branch_id) for node in roots]


def _build_subtree(node: dict, rev: int, branch_id: str) -> dict:
    """Recursively expand a spatial node into a tree dict."""
    children_data = get_spatial_children(node["global_id"], rev, branch_id)
    contained = get_contained_elements(node["global_id"], rev, branch_id)
    return {
        "global_id": node["global_id"],
        "ifc_class": node["ifc_class"],
        "name": node.get("name"),
        "children": [_build_subtree(c, rev, branch_id) for c in children_data],
        "contained_elements": contained,
    }


# ---------------------------------------------------------------------------
# Subgraph validation scoping
# ---------------------------------------------------------------------------


def get_entities_in_spatial_scope(
    scope_global_id: str | None,
    scope_name: str | None,
    rev: int,
    branch_id: str,
) -> list[str]:
    """Return global_ids of entities contained in a spatial container."""
    if scope_global_id:
        gid = _validate_id(scope_global_id)
        cypher = cypher_tpl.ENTITIES_IN_SPATIAL_SCOPE.format(
            scope_gid=gid,
            spatial_filter=_rev_filter("spatial", rev, branch_id),
            r_filter=_rev_filter("r", rev, branch_id),
            elem_filter=_rev_filter("elem", rev, branch_id),
        )
    elif scope_name:
        safe_name = _escape_cypher_string(scope_name)
        cypher = cypher_tpl.ENTITIES_IN_SPATIAL_SCOPE_BY_NAME.format(
            scope_name=safe_name,
            spatial_filter=_rev_filter("spatial", rev, branch_id),
            r_filter=_rev_filter("r", rev, branch_id),
            elem_filter=_rev_filter("elem", rev, branch_id),
        )
    else:
        return []

    cols = ["gid"]
    return [row[0] for row in _exec_cypher(cypher, cols)]


def get_entities_in_aggregate_scope(
    parent_global_id: str, rev: int, branch_id: str,
) -> list[str]:
    """Return global_ids of children via IfcRelAggregates."""
    gid = _validate_id(parent_global_id)
    cypher = cypher_tpl.ENTITIES_IN_AGGREGATE_SCOPE.format(
        parent_gid=gid,
        parent_filter=_rev_filter("parent", rev, branch_id),
        r_filter=_rev_filter("r", rev, branch_id),
        child_filter=_rev_filter("child", rev, branch_id),
    )
    cols = ["gid"]
    return [row[0] for row in _exec_cypher(cypher, cols)]


def get_entities_connected_via(
    source_global_id: str,
    rel_type: str,
    rev: int,
    branch_id: str,
) -> list[str]:
    """Return global_ids of entities connected via a specific relationship."""
    gid = _validate_id(source_global_id)
    label = _validate_label(rel_type)
    cypher = cypher_tpl.ENTITIES_CONNECTED_VIA.format(
        source_gid=gid,
        rel_type=label,
        source_filter=_rev_filter("source", rev, branch_id),
        r_filter=_rev_filter("r", rev, branch_id),
        target_filter=_rev_filter("target", rev, branch_id),
    )
    cols = ["gid"]
    return [row[0] for row in _exec_cypher(cypher, cols)]
