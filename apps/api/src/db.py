"""Postgres/AGE connection pool (psycopg2) and relational query helpers.

Provides a threaded connection pool, a cursor context-manager that handles
commit/rollback, and revision-scoped query functions for the SCD Type 2
``ifc_entity`` table, the ``revision`` table, the ``project`` /
``branch`` tables, and the ``filter_sets`` / ``branch_applied_filter_sets``
tables.

Temporal queries use ``revision_seq`` (a monotonic SERIAL on ``revision``)
for SCD Type 2 range comparisons, joined via the UUID FK columns
``created_in_revision_id`` / ``obsoleted_in_revision_id`` on ``ifc_entity``.
"""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from uuid import uuid4

import psycopg2
import psycopg2.extras
import psycopg2.pool

from .config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER

_pool: psycopg2.pool.ThreadedConnectionPool | None = None


# ---------------------------------------------------------------------------
# Connection pool lifecycle
# ---------------------------------------------------------------------------


def init_pool(minconn: int = 2, maxconn: int = 10) -> None:
    """Initialise the threaded connection pool. Called once at app startup."""
    global _pool
    _pool = psycopg2.pool.ThreadedConnectionPool(
        minconn,
        maxconn,
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )


def get_conn():
    """Get a connection from the pool."""
    if _pool is None:
        raise RuntimeError("Connection pool not initialised -- call init_pool() first")
    conn = _pool.getconn()
    # Set search path for AGE and our tables
    with conn.cursor() as cur:
        cur.execute('SET search_path = ag_catalog, "$user", public;')
    conn.commit()
    return conn


def put_conn(conn) -> None:
    """Return a connection to the pool."""
    if _pool is not None:
        _pool.putconn(conn)


def close_pool() -> None:
    """Close all connections in the pool. Called at app shutdown."""
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None


# ---------------------------------------------------------------------------
# Cursor context manager
# ---------------------------------------------------------------------------


@contextmanager
def get_cursor(dict_cursor: bool = False):
    """Yield a DB cursor with automatic commit/rollback and connection return.

    Usage::

        with get_cursor(dict_cursor=True) as cur:
            cur.execute("SELECT ...")
            rows = cur.fetchall()
    """
    conn = get_conn()
    factory = psycopg2.extras.RealDictCursor if dict_cursor else None
    cur = conn.cursor(cursor_factory=factory)
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        put_conn(conn)


# ---------------------------------------------------------------------------
# Project helpers
# ---------------------------------------------------------------------------


def create_project(name: str, description: str | None = None) -> dict:
    """Create a new project with a default 'main' branch. Returns the project dict."""
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            "INSERT INTO project (name, description) "
            "VALUES (%s, %s) "
            "RETURNING project_id, name, description, created_at",
            (name, description),
        )
        project = dict(cur.fetchone())

        cur.execute(
            "INSERT INTO branch (project_id, name) "
            "VALUES (%s, 'main') "
            "RETURNING branch_id, project_id, name, is_active, created_at",
            (project["project_id"],),
        )
    return project


def fetch_projects() -> list[dict]:
    """Return all projects ordered by created_at descending."""
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            "SELECT project_id, name, description, created_at "
            "FROM project ORDER BY created_at DESC"
        )
        return [dict(r) for r in cur.fetchall()]


def fetch_project(project_id: str) -> dict | None:
    """Return a single project by id."""
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            "SELECT project_id, name, description, created_at "
            "FROM project WHERE project_id = %s",
            (project_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# Branch helpers
# ---------------------------------------------------------------------------


def create_branch(project_id: str, name: str) -> dict:
    """Create a new branch within a project. Returns the branch dict."""
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            "INSERT INTO branch (project_id, name) "
            "VALUES (%s, %s) "
            "RETURNING branch_id, project_id, name, is_active, created_at",
            (project_id, name),
        )
        return dict(cur.fetchone())


def fetch_branches(project_id: str) -> list[dict]:
    """Return all branches for a project, ordered by created_at."""
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            "SELECT branch_id, project_id, name, is_active, created_at "
            "FROM branch WHERE project_id = %s ORDER BY created_at ASC",
            (project_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def fetch_branch(branch_id: str) -> dict | None:
    """Return a single branch by id."""
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            "SELECT branch_id, project_id, name, is_active, created_at "
            "FROM branch WHERE branch_id = %s",
            (branch_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def fetch_branch_by_name(project_id: str, name: str) -> dict | None:
    """Return a branch by project_id and name."""
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            "SELECT branch_id, project_id, name, is_active, created_at "
            "FROM branch WHERE project_id = %s AND name = %s",
            (project_id, name),
        )
        row = cur.fetchone()
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# Revision helpers (scoped to branch)
# ---------------------------------------------------------------------------


def get_latest_revision_seq(branch_id: str) -> int | None:
    """Return the highest ``revision_seq`` for a branch, or ``None`` if none exist."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT MAX(revision_seq) FROM revision WHERE branch_id = %s",
            (branch_id,),
        )
        row = cur.fetchone()
        return row[0] if row else None


def fetch_revisions(branch_id: str) -> list[dict]:
    """Return all revisions for a branch, ordered by revision_seq ascending."""
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            "SELECT revision_id, branch_id, revision_seq, parent_revision_id, "
            "ifc_filename, commit_message, author_id, created_at "
            "FROM revision WHERE branch_id = %s ORDER BY revision_seq ASC",
            (branch_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def fetch_revisions_filtered(
    branch_id: str,
    *,
    search: str | None = None,
    author_search: str | None = None,
    ifc_filename_search: str | None = None,
    commit_message_search: str | None = None,
    created_after: str | None = None,
    created_before: str | None = None,
) -> list[dict]:
    """Return revisions for a branch matching optional filters. All filters are parameterized.
    If search is set, it is OR-applied across author_id, ifc_filename, and commit_message.
    """
    base_sql = (
        "SELECT revision_id, branch_id, revision_seq, parent_revision_id, "
        "ifc_filename, commit_message, author_id, created_at "
        "FROM revision WHERE branch_id = %s"
    )
    params: list = [branch_id]
    conditions: list[str] = []

    if search is not None and search.strip():
        term = f"%{search.strip()}%"
        conditions.append(
            "(author_id::text ILIKE %s OR ifc_filename ILIKE %s OR commit_message ILIKE %s)"
        )
        params.extend([term, term, term])
    else:
        if author_search is not None and author_search.strip():
            conditions.append("author_id::text ILIKE %s")
            params.append(f"%{author_search.strip()}%")
        if ifc_filename_search is not None and ifc_filename_search.strip():
            conditions.append("ifc_filename ILIKE %s")
            params.append(f"%{ifc_filename_search.strip()}%")
        if commit_message_search is not None and commit_message_search.strip():
            conditions.append("commit_message ILIKE %s")
            params.append(f"%{commit_message_search.strip()}%")
    if created_after is not None and created_after.strip():
        conditions.append("created_at >= %s::timestamptz")
        params.append(created_after.strip())
    if created_before is not None and created_before.strip():
        conditions.append("created_at <= %s::timestamptz")
        params.append(created_before.strip())

    if conditions:
        base_sql += " AND " + " AND ".join(conditions)
    base_sql += " ORDER BY revision_seq ASC"

    with get_cursor(dict_cursor=True) as cur:
        cur.execute(base_sql, tuple(params))
        return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Entity queries -- branch + revision scoped (SCD Type 2)
# ---------------------------------------------------------------------------
# Temporal visibility is determined by joining ifc_entity with revision to
# compare revision_seq values.  _ENTITY_FROM provides the base FROM clause
# with the necessary JOINs; _REV_FILTER provides the WHERE fragment.

_ENTITY_COLS = (
    "e.ifc_global_id, e.ifc_class, e.attributes, e.geometry"
)

_ENTITY_FROM = (
    "ifc_entity e "
    "JOIN revision r_cr ON e.created_in_revision_id = r_cr.revision_id "
    "LEFT JOIN revision r_ob ON e.obsoleted_in_revision_id = r_ob.revision_id"
)

_REV_FILTER = (
    "r_cr.revision_seq <= %s "
    "AND (e.obsoleted_in_revision_id IS NULL OR r_ob.revision_seq > %s)"
)


def fetch_entity_at_revision(
    ifc_global_id: str, rev: int, branch_id: str,
) -> dict | None:
    """Fetch a single entity visible at *rev* on *branch_id*."""
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            f"SELECT {_ENTITY_COLS} FROM {_ENTITY_FROM} "
            f"WHERE e.ifc_global_id = %s AND e.branch_id = %s AND {_REV_FILTER} "
            f"LIMIT 1",
            (ifc_global_id, branch_id, rev, rev),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def fetch_entity_attributes_for_global_ids(
    rev: int, branch_id: str, global_ids: list[str],
) -> list[dict]:
    """Fetch ifc_global_id and attributes for entities visible at *rev* on *branch_id*.
    Returns list of dicts with keys ifc_global_id, attributes (JSONB as dict).
    """
    if not global_ids:
        return []
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            f"SELECT e.ifc_global_id, e.attributes FROM {_ENTITY_FROM} "
            f"WHERE e.branch_id = %s AND e.ifc_global_id = ANY(%s) AND {_REV_FILTER}",
            (branch_id, global_ids, rev, rev),
        )
        rows = cur.fetchall()
    result = []
    for r in rows:
        attrs = r.get("attributes") or {}
        if isinstance(attrs, str):
            attrs = json.loads(attrs)
        result.append({"ifc_global_id": r["ifc_global_id"], "attributes": attrs})
    return result


def fetch_shape_representations_for_product(
    product_global_id: str,
    rev: int,
    branch_id: str,
) -> list[dict]:
    """Fetch IfcShapeRepresentation entities for a single product at *rev* on *branch_id*."""
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            f"SELECT {_ENTITY_COLS} FROM {_ENTITY_FROM} "
            f"WHERE e.branch_id = %s "
            f"AND e.ifc_class = %s "
            f"AND e.attributes->>'OfProduct' = %s "
            f"AND {_REV_FILTER}",
            (branch_id, "IfcShapeRepresentation", product_global_id, rev, rev),
        )
        return [dict(r) for r in cur.fetchall()]


def fetch_shape_reps_for_products(
    product_global_ids: list[str],
    rev: int,
    branch_id: str,
) -> dict[str, list[dict]]:
    """Batch-fetch shape reps for many products, grouped by owning product GlobalId."""
    if not product_global_ids:
        return {}

    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            f"SELECT {_ENTITY_COLS} FROM {_ENTITY_FROM} "
            f"WHERE e.branch_id = %s "
            f"AND e.ifc_class = %s "
            f"AND e.attributes->>'OfProduct' = ANY(%s) "
            f"AND {_REV_FILTER}",
            (branch_id, "IfcShapeRepresentation", product_global_ids, rev, rev),
        )
        rows = [dict(r) for r in cur.fetchall()]

    grouped: dict[str, list[dict]] = {}
    for row in rows:
        attrs = row.get("attributes") or {}
        if isinstance(attrs, str):
            attrs = json.loads(attrs)
        owner = attrs.get("OfProduct")
        if not owner:
            continue
        grouped.setdefault(owner, []).append(row)
    return grouped


def _resolve_relation_gids(
    relation_types: list[str], rev: int, branch_id: str,
) -> list[str]:
    """Query the AGE graph for entity global_ids connected via *relation_types*."""
    from .services.graph.age_client import get_product_ids_by_relation

    all_gids: set[str] = set()
    for rt in relation_types:
        all_gids.update(get_product_ids_by_relation(rt, rev, branch_id))
    return list(all_gids)


def fetch_entities_at_revision(
    rev: int,
    branch_id: str,
    ifc_class: str | None = None,
    ifc_classes: list[str] | None = None,
    contained_in: str | None = None,
    name: str | None = None,
    object_type: str | None = None,
    tag: str | None = None,
    description: str | None = None,
    global_id: str | None = None,
    relation_types: list[str] | None = None,
) -> list[dict]:
    """List entities visible at *rev* on *branch_id*, optionally filtered."""
    clauses: list[str] = ["e.branch_id = %s", _REV_FILTER]
    params: list = [branch_id, rev, rev]

    if ifc_classes is not None and len(ifc_classes) > 0:
        clauses.append("e.ifc_class = ANY(%s)")
        params.append(ifc_classes)
    elif ifc_class is not None:
        clauses.append("e.ifc_class = %s")
        params.append(ifc_class)
    if contained_in is not None:
        clauses.append("e.attributes->>'ContainedIn' = %s")
        params.append(contained_in)
    if name is not None:
        clauses.append("e.attributes->>'Name' ILIKE %s")
        params.append(f"%{name}%")
    if object_type is not None:
        clauses.append("e.attributes->>'ObjectType' ILIKE %s")
        params.append(f"%{object_type}%")
    if tag is not None:
        clauses.append("e.attributes->>'Tag' ILIKE %s")
        params.append(f"%{tag}%")
    if description is not None:
        clauses.append("e.attributes->>'Description' ILIKE %s")
        params.append(f"%{description}%")
    if global_id is not None:
        clauses.append("e.ifc_global_id ILIKE %s")
        params.append(f"%{global_id}%")
    if relation_types:
        gids = _resolve_relation_gids(relation_types, rev, branch_id)
        if gids:
            clauses.append("e.ifc_global_id = ANY(%s)")
            params.append(gids)
        else:
            return []

    where = " AND ".join(clauses)
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            f"SELECT {_ENTITY_COLS} FROM {_ENTITY_FROM} WHERE {where}",
            params,
        )
        return [dict(r) for r in cur.fetchall()]


def fetch_distinct_ifc_classes_at_revision(rev: int, branch_id: str) -> list[str]:
    """Return distinct ``ifc_class`` values visible at *rev* on *branch_id*."""
    with get_cursor() as cur:
        cur.execute(
            f"SELECT DISTINCT e.ifc_class FROM {_ENTITY_FROM} "
            f"WHERE e.branch_id = %s AND {_REV_FILTER}",
            (branch_id, rev, rev),
        )
        rows = cur.fetchall()
    return [row[0] for row in rows]


def fetch_common_attribute_keys(rev: int, branch_id: str, limit: int = 50) -> list[str]:
    """Return the most common top-level JSONB attribute keys across entities."""
    with get_cursor() as cur:
        cur.execute(
            f"SELECT k, COUNT(*) AS cnt "
            f"FROM {_ENTITY_FROM}, "
            f"LATERAL jsonb_object_keys(COALESCE(e.attributes, '{{}}'::jsonb)) AS k "
            f"WHERE e.branch_id = %s AND {_REV_FILTER} "
            f"GROUP BY k ORDER BY cnt DESC LIMIT %s",
            (branch_id, rev, rev, limit),
        )
        return [row[0] for row in cur.fetchall()]


def fetch_entity_count_at_revision(rev: int, branch_id: str) -> int:
    """Return the total number of entities visible at *rev* on *branch_id*."""
    with get_cursor() as cur:
        cur.execute(
            f"SELECT COUNT(*) FROM {_ENTITY_FROM} "
            f"WHERE e.branch_id = %s AND {_REV_FILTER}",
            (branch_id, rev, rev),
        )
        return cur.fetchone()[0]


def fetch_spatial_container(
    contained_in_gid: str | None, rev: int, branch_id: str,
) -> dict | None:
    """Fetch the spatial container for an element (by contained_in GlobalId)."""
    if not contained_in_gid:
        return None
    return fetch_entity_at_revision(contained_in_gid, rev, branch_id)


# ---------------------------------------------------------------------------
# Revision diff -- state comparison between two revisions (same branch)
# ---------------------------------------------------------------------------


def fetch_revision_diff(from_rev: int, to_rev: int, branch_id: str) -> dict:
    """Compare visible entities between *from_rev* and *to_rev* on a branch.

    Returns ``{"added": [...], "modified": [...], "deleted": [...]}`` where
    each element is a dict with ``ifc_global_id``, ``ifc_class``, ``name``.
    """
    with get_cursor(dict_cursor=True) as cur:
        # Added: visible at to_rev but not at from_rev
        cur.execute(
            "SELECT t.ifc_global_id, t.ifc_class, "
            "t.attributes->>'Name' AS name "
            "FROM ifc_entity t "
            "JOIN revision t_cr ON t.created_in_revision_id = t_cr.revision_id "
            "LEFT JOIN revision t_ob ON t.obsoleted_in_revision_id = t_ob.revision_id "
            "WHERE t.branch_id = %s "
            "  AND t_cr.revision_seq <= %s "
            "  AND (t.obsoleted_in_revision_id IS NULL OR t_ob.revision_seq > %s) "
            "  AND NOT EXISTS ("
            "      SELECT 1 FROM ifc_entity f "
            "      JOIN revision f_cr ON f.created_in_revision_id = f_cr.revision_id "
            "      LEFT JOIN revision f_ob ON f.obsoleted_in_revision_id = f_ob.revision_id "
            "      WHERE f.branch_id = %s "
            "        AND f.ifc_global_id = t.ifc_global_id "
            "        AND f_cr.revision_seq <= %s "
            "        AND (f.obsoleted_in_revision_id IS NULL OR f_ob.revision_seq > %s)"
            "  )",
            (branch_id, to_rev, to_rev, branch_id, from_rev, from_rev),
        )
        added = [dict(r) for r in cur.fetchall()]

        # Deleted: visible at from_rev but not at to_rev
        cur.execute(
            "SELECT f.ifc_global_id, f.ifc_class, "
            "f.attributes->>'Name' AS name "
            "FROM ifc_entity f "
            "JOIN revision f_cr ON f.created_in_revision_id = f_cr.revision_id "
            "LEFT JOIN revision f_ob ON f.obsoleted_in_revision_id = f_ob.revision_id "
            "WHERE f.branch_id = %s "
            "  AND f_cr.revision_seq <= %s "
            "  AND (f.obsoleted_in_revision_id IS NULL OR f_ob.revision_seq > %s) "
            "  AND NOT EXISTS ("
            "      SELECT 1 FROM ifc_entity t "
            "      JOIN revision t_cr ON t.created_in_revision_id = t_cr.revision_id "
            "      LEFT JOIN revision t_ob ON t.obsoleted_in_revision_id = t_ob.revision_id "
            "      WHERE t.branch_id = %s "
            "        AND t.ifc_global_id = f.ifc_global_id "
            "        AND t_cr.revision_seq <= %s "
            "        AND (t.obsoleted_in_revision_id IS NULL OR t_ob.revision_seq > %s)"
            "  )",
            (branch_id, from_rev, from_rev, branch_id, to_rev, to_rev),
        )
        deleted = [dict(r) for r in cur.fetchall()]

        # Modified: visible at both but with different content_hash
        cur.execute(
            "SELECT t.ifc_global_id, t.ifc_class, "
            "t.attributes->>'Name' AS name "
            "FROM ifc_entity t "
            "JOIN revision t_cr ON t.created_in_revision_id = t_cr.revision_id "
            "LEFT JOIN revision t_ob ON t.obsoleted_in_revision_id = t_ob.revision_id "
            "JOIN ifc_entity f "
            "  ON t.ifc_global_id = f.ifc_global_id AND f.branch_id = %s "
            "JOIN revision f_cr ON f.created_in_revision_id = f_cr.revision_id "
            "LEFT JOIN revision f_ob ON f.obsoleted_in_revision_id = f_ob.revision_id "
            "WHERE t.branch_id = %s "
            "  AND t_cr.revision_seq <= %s "
            "  AND (t.obsoleted_in_revision_id IS NULL OR t_ob.revision_seq > %s) "
            "  AND f_cr.revision_seq <= %s "
            "  AND (f.obsoleted_in_revision_id IS NULL OR f_ob.revision_seq > %s) "
            "  AND t.content_hash != f.content_hash",
            (branch_id, branch_id, to_rev, to_rev, from_rev, from_rev),
        )
        modified = [dict(r) for r in cur.fetchall()]

    return {"added": added, "modified": modified, "deleted": deleted}


# ---------------------------------------------------------------------------
# Filter set CRUD
# ---------------------------------------------------------------------------

_FILTER_SET_COLS = (
    "filter_set_id, branch_id, name, logic, filters, color, created_at, updated_at"
)


_DEFAULT_FILTER_SET_COLORS = [
    "#4A90D9", "#E67E22", "#2ECC71", "#E74C3C",
    "#9B59B6", "#1ABC9C", "#F1C40F", "#E91E63",
]


def _next_default_color(branch_id: str) -> str:
    """Pick the next default color for a new filter set on a branch."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM filter_sets WHERE branch_id = %s",
            (branch_id,),
        )
        count = cur.fetchone()[0]
    return _DEFAULT_FILTER_SET_COLORS[count % len(_DEFAULT_FILTER_SET_COLORS)]


def create_filter_set(
    branch_id: str, name: str, logic: str, filters_json: list[dict],
    color: str | None = None,
) -> dict:
    """Create a new filter set on a branch. Returns the new row."""
    if color is None:
        color = _next_default_color(branch_id)
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            f"INSERT INTO filter_sets (branch_id, name, logic, filters, color) "
            f"VALUES (%s, %s, %s, %s, %s) RETURNING {_FILTER_SET_COLS}",
            (branch_id, name, logic, json.dumps(filters_json), color),
        )
        return dict(cur.fetchone())


def update_filter_set(
    filter_set_id: str,
    name: str | None = None,
    logic: str | None = None,
    filters_json: list[dict] | None = None,
    color: str | None = None,
) -> dict | None:
    """Update specified fields on a filter set. Returns the updated row."""
    sets: list[str] = ["updated_at = now()"]
    params: list = []
    if name is not None:
        sets.append("name = %s")
        params.append(name)
    if logic is not None:
        sets.append("logic = %s")
        params.append(logic)
    if filters_json is not None:
        sets.append("filters = %s")
        params.append(json.dumps(filters_json))
    if color is not None:
        sets.append("color = %s")
        params.append(color)
    params.append(filter_set_id)
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            f"UPDATE filter_sets SET {', '.join(sets)} WHERE filter_set_id = %s "
            f"RETURNING {_FILTER_SET_COLS}",
            params,
        )
        row = cur.fetchone()
        return dict(row) if row else None


def delete_filter_set(filter_set_id: str) -> bool:
    """Delete a filter set by id. Returns True if a row was deleted."""
    with get_cursor() as cur:
        cur.execute(
            "DELETE FROM filter_sets WHERE filter_set_id = %s", (filter_set_id,),
        )
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Delete project / branch / revision
# ---------------------------------------------------------------------------


def delete_project(project_id: str) -> bool:
    """Delete a project and all its branches, revisions, and graph data.

    Fetches branch IDs for graph cleanup, deletes AGE graph data per branch,
    then deletes the project (CASCADE removes branches, revisions, ifc_entity,
    filter_sets). Returns True if a row was deleted.
    """
    from .services.graph.age_client import delete_branch_graph_data

    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            "SELECT branch_id FROM branch WHERE project_id = %s", (project_id,),
        )
        branch_ids = [r["branch_id"] for r in cur.fetchall()]
    for bid in branch_ids:
        delete_branch_graph_data(bid)
    with get_cursor() as cur:
        cur.execute("DELETE FROM project WHERE project_id = %s", (project_id,))
        return cur.rowcount > 0


def delete_branch(branch_id: str) -> bool:
    """Delete a branch and all its revisions and graph data.

    Deletes AGE graph data for the branch, then deletes the branch (CASCADE
    removes revisions, ifc_entity, filter_sets). Returns True if a row was
    deleted.
    """
    from .services.graph.age_client import delete_branch_graph_data

    delete_branch_graph_data(branch_id)
    with get_cursor() as cur:
        cur.execute("DELETE FROM branch WHERE branch_id = %s", (branch_id,))
        return cur.rowcount > 0


def delete_revision(revision_id: str) -> bool:
    """Delete a revision and clean up ifc_entity rows that reference it.

    Removes ifc_entity rows where created_in_revision_id = revision_id, sets
    obsoleted_in_revision_id = NULL where it matched, then deletes the
    revision. Returns True if a row was deleted.
    """
    with get_cursor() as cur:
        cur.execute(
            "DELETE FROM ifc_entity WHERE created_in_revision_id = %s",
            (revision_id,),
        )
        cur.execute(
            "UPDATE ifc_entity SET obsoleted_in_revision_id = NULL "
            "WHERE obsoleted_in_revision_id = %s",
            (revision_id,),
        )
        cur.execute(
            "DELETE FROM revision WHERE revision_id = %s", (revision_id,),
        )
        return cur.rowcount > 0


def fetch_filter_set(filter_set_id: str) -> dict | None:
    """Fetch a single filter set by id."""
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            f"SELECT {_FILTER_SET_COLS} FROM filter_sets WHERE filter_set_id = %s",
            (filter_set_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def fetch_filter_sets_for_branch(branch_id: str) -> list[dict]:
    """Return all filter sets for a branch, newest first."""
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            f"SELECT {_FILTER_SET_COLS} FROM filter_sets "
            f"WHERE branch_id = %s ORDER BY updated_at DESC",
            (branch_id,),
        )
        return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Sheet template CRUD (project-scoped bottom-sheet state)
# ---------------------------------------------------------------------------

_SHEET_TEMPLATE_COLS = (
    "sheet_template_id, project_id, name, sheet, open, created_at, updated_at"
)


def create_sheet_template(
    project_id: str, name: str, sheet_json: dict, *, open: bool = False,
) -> dict:
    """Create a new sheet template for a project. Returns the new row."""
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            "INSERT INTO sheet_template (project_id, name, sheet, open) "
            f"VALUES (%s, %s, %s, %s) RETURNING {_SHEET_TEMPLATE_COLS}",
            (project_id, name, json.dumps(sheet_json), open),
        )
        row = cur.fetchone()
        r = dict(row)
        if isinstance(r.get("sheet"), str):
            r["sheet"] = json.loads(r["sheet"]) if r["sheet"] else {}
        return r


def fetch_sheet_template(sheet_template_id: str) -> dict | None:
    """Fetch a single sheet template by id."""
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            f"SELECT {_SHEET_TEMPLATE_COLS} FROM sheet_template "
            "WHERE sheet_template_id = %s",
            (sheet_template_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        r = dict(row)
        if isinstance(r.get("sheet"), str):
            r["sheet"] = json.loads(r["sheet"]) if r["sheet"] else {}
        return r


def update_sheet_template(
    sheet_template_id: str,
    *,
    open: bool | None = None,
    name: str | None = None,
    sheet: dict | None = None,
) -> dict | None:
    """Update a sheet template. Returns the updated row or None if not found."""
    updates: list[str] = []
    params: list = []
    if open is not None:
        updates.append("open = %s")
        params.append(open)
    if name is not None:
        updates.append("name = %s")
        params.append(name)
    if sheet is not None:
        updates.append("sheet = %s")
        params.append(json.dumps(sheet))
    if not updates:
        return fetch_sheet_template(sheet_template_id)
    updates.append("updated_at = now()")
    params.append(sheet_template_id)
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            f"UPDATE sheet_template SET {', '.join(updates)} "
            "WHERE sheet_template_id = %s",
            params,
        )
    return fetch_sheet_template(sheet_template_id)


def fetch_sheet_templates_opened(project_id: str) -> list[dict]:
    """Return sheet templates with open=True for a project, by updated_at."""
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            f"SELECT {_SHEET_TEMPLATE_COLS} FROM sheet_template "
            "WHERE project_id = %s AND open = TRUE ORDER BY updated_at ASC",
            (project_id,),
        )
        rows = [dict(r) for r in cur.fetchall()]
    for r in rows:
        if isinstance(r.get("sheet"), str):
            r["sheet"] = json.loads(r["sheet"]) if r["sheet"] else {}
    return rows


def fetch_sheet_templates_for_project(project_id: str) -> list[dict]:
    """Return all sheet templates for a project, newest first."""
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            f"SELECT {_SHEET_TEMPLATE_COLS} FROM sheet_template "
            "WHERE project_id = %s ORDER BY updated_at DESC",
            (project_id,),
        )
        rows = [dict(r) for r in cur.fetchall()]
    for r in rows:
        if isinstance(r.get("sheet"), str):
            r["sheet"] = json.loads(r["sheet"]) if r["sheet"] else {}
    return rows


def search_sheet_templates(query: str, project_id: str) -> list[dict]:
    """Search sheet templates by name within a project."""
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            f"SELECT {_SHEET_TEMPLATE_COLS} FROM sheet_template "
            "WHERE project_id = %s AND name ILIKE %s ORDER BY updated_at DESC",
            (project_id, f"%{query}%"),
        )
        rows = [dict(r) for r in cur.fetchall()]
    for r in rows:
        if isinstance(r.get("sheet"), str):
            r["sheet"] = json.loads(r["sheet"]) if r["sheet"] else {}
    return rows


def delete_sheet_template(sheet_template_id: str) -> bool:
    """Delete a sheet template by id. Returns True if a row was deleted."""
    with get_cursor() as cur:
        cur.execute(
            "DELETE FROM sheet_template WHERE sheet_template_id = %s",
            (sheet_template_id,),
        )
        return cur.rowcount > 0


def search_filter_sets(
    query: str,
    branch_id: str | None = None,
    project_id: str | None = None,
) -> list[dict]:
    """Search filter sets by name with optional scope narrowing.

    - *branch_id* only: filter sets on that branch.
    - *project_id* only: filter sets on any branch of that project.
    - Neither: search across all filter sets.
    """
    clauses: list[str] = ["fs.name ILIKE %s"]
    params: list = [f"%{query}%"]

    if branch_id is not None:
        clauses.append("fs.branch_id = %s")
        params.append(branch_id)
    elif project_id is not None:
        clauses.append("b.project_id = %s")
        params.append(project_id)

    needs_join = project_id is not None and branch_id is None
    join = "JOIN branch b ON fs.branch_id = b.branch_id" if needs_join else ""
    where = " AND ".join(clauses)

    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            f"SELECT fs.filter_set_id, fs.branch_id, fs.name, fs.logic, "
            f"fs.filters, fs.color, fs.created_at, fs.updated_at "
            f"FROM filter_sets fs {join} WHERE {where} ORDER BY fs.updated_at DESC",
            params,
        )
        return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Applied filter sets (tracks active filter sets per branch)
# ---------------------------------------------------------------------------


def apply_filter_sets(
    branch_id: str, filter_set_ids: list[str], combination_logic: str,
) -> None:
    """Replace the applied filter sets for a branch.

    The list order of *filter_set_ids* determines ``display_order`` (0-based),
    which controls priority when an entity matches multiple sets.
    """
    with get_cursor() as cur:
        cur.execute(
            "DELETE FROM branch_applied_filter_sets WHERE branch_id = %s",
            (branch_id,),
        )
        for idx, fs_id in enumerate(filter_set_ids):
            cur.execute(
                "INSERT INTO branch_applied_filter_sets "
                "(branch_id, filter_set_id, combination_logic, display_order) "
                "VALUES (%s, %s, %s, %s)",
                (branch_id, fs_id, combination_logic, idx),
            )


def fetch_applied_filter_sets(branch_id: str) -> dict:
    """Return the currently applied filter sets for a branch.

    Returns ``{"filter_sets": [...], "combination_logic": "AND"|"OR"}``.
    Filter sets are ordered by ``display_order`` (ascending).
    """
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            "SELECT ba.combination_logic, ba.display_order, "
            "fs.filter_set_id, fs.branch_id, fs.name, fs.logic, fs.filters, "
            "fs.color, fs.created_at, fs.updated_at "
            "FROM branch_applied_filter_sets ba "
            "JOIN filter_sets fs ON ba.filter_set_id = fs.filter_set_id "
            "WHERE ba.branch_id = %s ORDER BY ba.display_order ASC",
            (branch_id,),
        )
        rows = [dict(r) for r in cur.fetchall()]

    if not rows:
        return {"filter_sets": [], "combination_logic": "AND"}

    combination_logic = rows[0]["combination_logic"]
    filter_sets = [
        {
            "filter_set_id": r["filter_set_id"],
            "branch_id": r["branch_id"],
            "name": r["name"],
            "logic": r["logic"],
            "filters": r["filters"],
            "color": r["color"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]
    return {"filter_sets": filter_sets, "combination_logic": combination_logic}


# ---------------------------------------------------------------------------
# Entity filtering with structured filter sets
# ---------------------------------------------------------------------------

def _escape_ilike(value: str) -> str:
    """Escape % and _ for safe use in ILIKE patterns."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _is_global_id_attribute(attr: str) -> bool:
    """Return True when the requested attribute should map to e.ifc_global_id."""
    compact = "".join(ch for ch in attr.lower() if ch.isalnum())
    return compact in {"globalid", "ifcglobalid"}


def _build_attribute_value_source(attr: str, value_type: str) -> str:
    """Return SQL subquery (text_value column) for a nested attribute key + value type."""
    if _is_global_id_attribute(attr):
        if value_type == "object":
            return "(SELECT NULL::text AS text_value WHERE FALSE)"
        return "(SELECT e.ifc_global_id::text AS text_value)"

    walk_sql = """
    (
        WITH RECURSIVE walk(node, key_name, key_value) AS (
            SELECT e.attributes, NULL::text, NULL::jsonb
            UNION ALL
            SELECT child.value, child.key_name, child.value
            FROM walk
            JOIN LATERAL (
                SELECT kv.key AS key_name, kv.value
                FROM jsonb_each(
                    CASE
                        WHEN jsonb_typeof(walk.node) = 'object' THEN walk.node
                        ELSE '{}'::jsonb
                    END
                ) AS kv
                UNION ALL
                SELECT NULL::text AS key_name, arr.value
                FROM jsonb_array_elements(
                    CASE
                        WHEN jsonb_typeof(walk.node) = 'array' THEN walk.node
                        ELSE '[]'::jsonb
                    END
                ) AS arr(value)
            ) AS child ON TRUE
        ),
        attr_matches(node) AS (
            SELECT walk.key_value
            FROM walk
            WHERE walk.key_name IS NOT NULL
              AND lower(walk.key_name) = lower(%s)
        ),
        descendants(node) AS (
            SELECT node FROM attr_matches
            UNION ALL
            SELECT child.value
            FROM descendants d
            JOIN LATERAL (
                SELECT kv.value
                FROM jsonb_each(
                    CASE
                        WHEN jsonb_typeof(d.node) = 'object' THEN d.node
                        ELSE '{}'::jsonb
                    END
                ) AS kv
                UNION ALL
                SELECT arr.value
                FROM jsonb_array_elements(
                    CASE
                        WHEN jsonb_typeof(d.node) = 'array' THEN d.node
                        ELSE '[]'::jsonb
                    END
                ) AS arr(value)
            ) AS child ON TRUE
        )
    """
    if value_type == "numeric":
        return (
            walk_sql
            + """
        SELECT descendants.node #>> '{}' AS text_value
        FROM descendants
        WHERE jsonb_typeof(descendants.node) IN ('number', 'string')
    )
    """
        )
    if value_type == "object":
        return (
            walk_sql
            + """
        SELECT keys.key_name AS text_value
        FROM descendants
        JOIN LATERAL (
            SELECT obj_keys.key_name
            FROM jsonb_object_keys(
                CASE
                    WHEN jsonb_typeof(descendants.node) = 'object' THEN descendants.node
                    ELSE '{}'::jsonb
                END
            ) AS obj_keys(key_name)
        ) AS keys ON TRUE
    )
    """
        )
    # default: string
    return (
        walk_sql
        + """
        SELECT
            descendants.node #>> '{}' AS text_value
        FROM descendants
        WHERE jsonb_typeof(descendants.node) = 'string'
    )
    """
    )


def _build_class_clause(f: dict, params: list) -> str | None:
    """Build SQL for class mode: exact match or inherits_from (class + descendants)."""
    from .schema.filter_operators import (
        CLASS_OPERATORS,
        resolve_operator,
    )
    from .schema.ifc_schema_loader import get_descendants

    ifc_class = f.get("ifcClass") or f.get("ifc_class")
    if not ifc_class:
        return None
    op = resolve_operator(f)
    if op not in CLASS_OPERATORS:
        op = "is"
    if op == "inherits_from":
        classes = get_descendants(ifc_class, include_self=True, concrete_only=True)
        if not classes:
            return "FALSE"
        params.append(classes)
        return "e.ifc_class = ANY(%s)"
    if op == "is_not":
        params.append(ifc_class)
        return "e.ifc_class != %s"
    # is (exact)
    params.append(ifc_class)
    return "e.ifc_class = %s"


def _build_attribute_clause(f: dict, params: list) -> str | None:
    """Build SQL for attribute mode across nested attributes JSONB keys."""
    from .schema.filter_operators import (
        NUMERIC_OPERATORS,
        STRING_OPERATORS,
        resolve_operator,
        value_required_for_operator,
    )

    attr = f.get("attribute")
    if not attr:
        return None
    op = resolve_operator(f)
    value = f.get("value")
    value_type = (f.get("valueType") or f.get("value_type") or "string").lower()

    needs_value = value_required_for_operator(op)
    if needs_value and (value is None or (isinstance(value, str) and value.strip() == "")):
        return None

    attr = str(attr).strip()
    if not attr:
        return None
    source_sql = _build_attribute_value_source(attr, value_type)
    is_gid = _is_global_id_attribute(attr)

    def src() -> str:
        """Embed source_sql and append the attr bind param in correct position."""
        if not is_gid:
            params.append(attr)
        return source_sql

    # Numeric operators
    if value_type == "numeric" and op in NUMERIC_OPERATORS:
        try:
            num_val = float(value) if value else None
        except (TypeError, ValueError):
            return None
        if num_val is None:
            return None
        num_regex = r"^-?[0-9]+\.?[0-9]*([eE][+-]?[0-9]+)?$"
        numeric_exists = (
            f"EXISTS (SELECT 1 FROM {src()} AS attr_values "
            f"WHERE attr_values.text_value ~ '{num_regex}')"
        )
        if op == "equals":
            s = src()
            params.append(num_val)
            return (
                f"({numeric_exists} AND EXISTS (SELECT 1 FROM {s} AS attr_values "
                f"WHERE attr_values.text_value ~ '{num_regex}' "
                f"AND (attr_values.text_value)::numeric = %s))"
            )
        if op == "not_equals":
            s = src()
            params.append(num_val)
            return (
                f"({numeric_exists} AND NOT EXISTS (SELECT 1 FROM {s} AS attr_values "
                f"WHERE attr_values.text_value ~ '{num_regex}' "
                f"AND (attr_values.text_value)::numeric = %s))"
            )
        if op == "gt":
            s = src()
            params.append(num_val)
            return (
                f"({numeric_exists} AND EXISTS (SELECT 1 FROM {s} AS attr_values "
                f"WHERE attr_values.text_value ~ '{num_regex}' "
                f"AND (attr_values.text_value)::numeric > %s))"
            )
        if op == "lt":
            s = src()
            params.append(num_val)
            return (
                f"({numeric_exists} AND EXISTS (SELECT 1 FROM {s} AS attr_values "
                f"WHERE attr_values.text_value ~ '{num_regex}' "
                f"AND (attr_values.text_value)::numeric < %s))"
            )
        if op == "gte":
            s = src()
            params.append(num_val)
            return (
                f"({numeric_exists} AND EXISTS (SELECT 1 FROM {s} AS attr_values "
                f"WHERE attr_values.text_value ~ '{num_regex}' "
                f"AND (attr_values.text_value)::numeric >= %s))"
            )
        if op == "lte":
            s = src()
            params.append(num_val)
            return (
                f"({numeric_exists} AND EXISTS (SELECT 1 FROM {s} AS attr_values "
                f"WHERE attr_values.text_value ~ '{num_regex}' "
                f"AND (attr_values.text_value)::numeric <= %s))"
            )

    # String operators (default)
    if op not in STRING_OPERATORS:
        op = "contains"

    if op == "is_empty":
        return (
            f"EXISTS (SELECT 1 FROM {src()} AS attr_values "
            f"WHERE attr_values.text_value IS NULL OR attr_values.text_value = '')"
        )
    if op == "is_not_empty":
        return (
            f"EXISTS (SELECT 1 FROM {src()} AS attr_values "
            f"WHERE attr_values.text_value IS NOT NULL AND attr_values.text_value != '')"
        )

    if not value:
        return None

    if op == "is":
        s = src()
        params.append(_escape_ilike(str(value)))
        return (
            f"EXISTS (SELECT 1 FROM {s} AS attr_values "
            f"WHERE attr_values.text_value IS NOT NULL AND attr_values.text_value ILIKE %s)"
        )
    if op == "is_not":
        s1 = src()
        s2 = src()
        params.append(_escape_ilike(str(value)))
        return (
            f"(EXISTS (SELECT 1 FROM {s1} AS attr_values) "
            f"AND NOT EXISTS (SELECT 1 FROM {s2} AS attr_values "
            f"WHERE attr_values.text_value IS NOT NULL AND attr_values.text_value ILIKE %s))"
        )
    if op == "contains":
        s = src()
        params.append(f"%{_escape_ilike(str(value))}%")
        return (
            f"EXISTS (SELECT 1 FROM {s} AS attr_values "
            f"WHERE attr_values.text_value IS NOT NULL AND attr_values.text_value ILIKE %s)"
        )
    if op == "not_contains":
        s1 = src()
        s2 = src()
        params.append(f"%{_escape_ilike(str(value))}%")
        return (
            f"(EXISTS (SELECT 1 FROM {s1} AS attr_values) "
            f"AND NOT EXISTS (SELECT 1 FROM {s2} AS attr_values "
            f"WHERE attr_values.text_value IS NOT NULL AND attr_values.text_value ILIKE %s))"
        )
    if op == "starts_with":
        s = src()
        params.append(f"{_escape_ilike(str(value))}%")
        return (
            f"EXISTS (SELECT 1 FROM {s} AS attr_values "
            f"WHERE attr_values.text_value IS NOT NULL AND attr_values.text_value ILIKE %s)"
        )
    if op == "ends_with":
        s = src()
        params.append(f"%{_escape_ilike(str(value))}")
        return (
            f"EXISTS (SELECT 1 FROM {s} AS attr_values "
            f"WHERE attr_values.text_value IS NOT NULL AND attr_values.text_value ILIKE %s)"
        )

    return None


def _build_relation_clause(f: dict, params: list, rev: int, branch_id: str) -> str | None:
    """Build SQL for relation mode (AGE-resolved GID set)."""
    relation = f.get("relation")
    if not relation or not rev or not branch_id:
        return None
    gids = _resolve_relation_gids([relation], rev, branch_id)
    if not gids:
        return "FALSE"
    params.append(gids)
    return "e.ifc_global_id = ANY(%s)"


def _build_filter_clause(
    f: dict, params: list, rev: int = 0, branch_id: str = "",
) -> str | None:
    """Convert a single filter dict into a SQL clause, appending bind params.

    Attribute filters target JSONB keys in ``ifc_entity.attributes`` via the
    ``->>`` operator, except ``globalId`` which maps to the ``ifc_global_id``
    column directly.  Class filters target ``ifc_class``.
    """
    mode = f.get("mode") or "class"
    if mode == "class":
        return _build_class_clause(f, params)
    if mode == "attribute":
        return _build_attribute_clause(f, params)
    if mode == "relation":
        return _build_relation_clause(f, params, rev, branch_id)
    return None


def fetch_entities_with_filter_sets(
    rev: int,
    branch_id: str,
    filter_sets_data: list[dict],
    combination_logic: str = "AND",
) -> list[dict]:
    """Query entities matching multiple filter sets with configurable logic.

    Each entry in *filter_sets_data* has keys ``logic`` (``"AND"``/``"OR"``)
    and ``filters`` (list of filter dicts).  Conditions within a set are
    joined by the set's ``logic``; the resulting groups are joined by
    *combination_logic*.
    """
    from .schema.filter_operators import normalize_logic

    base_clauses: list[str] = ["e.branch_id = %s", _REV_FILTER]
    params: list = [branch_id, rev, rev]

    group_sqls: list[str] = []
    for fs in filter_sets_data:
        fs_logic = normalize_logic(fs.get("logic"))
        filter_clauses: list[str] = []
        for f in fs.get("filters", []):
            clause = _build_filter_clause(f, params, rev=rev, branch_id=branch_id)
            if clause:
                filter_clauses.append(clause)
        if filter_clauses:
            joiner = f" {fs_logic} "
            group_sqls.append(f"({joiner.join(filter_clauses)})")

    if group_sqls:
        set_joiner = f" {normalize_logic(combination_logic)} "
        base_clauses.append(f"({set_joiner.join(group_sqls)})")

    where = " AND ".join(base_clauses)
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            f"SELECT {_ENTITY_COLS} FROM {_ENTITY_FROM} WHERE {where}",
            params,
        )
        return [dict(r) for r in cur.fetchall()]


def fetch_filter_set_matches(
    rev: int,
    branch_id: str,
    filter_sets_data: list[dict],
) -> list[dict]:
    """Return per-filter-set matching entity global IDs.

    Each entry in *filter_sets_data* must have ``filter_set_id``, ``logic``,
    and ``filters``.  Returns a list of dicts
    ``{"filter_set_id": ..., "global_ids": [...]}``, preserving input order.
    """
    from .schema.filter_operators import normalize_logic

    results: list[dict] = []
    for fs in filter_sets_data:
        fs_id = fs.get("filter_set_id") or fs.get("id")
        fs_logic = normalize_logic(fs.get("logic"))
        clauses: list[str] = ["e.branch_id = %s", _REV_FILTER]
        params: list = [branch_id, rev, rev]

        filter_clauses: list[str] = []
        for f in fs.get("filters", []):
            clause = _build_filter_clause(f, params, rev=rev, branch_id=branch_id)
            if clause:
                filter_clauses.append(clause)

        if filter_clauses:
            joiner = f" {fs_logic} "
            clauses.append(f"({joiner.join(filter_clauses)})")

        where = " AND ".join(clauses)
        with get_cursor() as cur:
            cur.execute(
                f"SELECT e.ifc_global_id FROM {_ENTITY_FROM} WHERE {where}",
                params,
            )
            gids = [row[0] for row in cur.fetchall()]

        results.append({"filter_set_id": fs_id, "global_ids": gids})
    return results


# ---------------------------------------------------------------------------
# Validation rules / IFC schema metadata
# ---------------------------------------------------------------------------


def fetch_validation_rules(schema_name: str) -> dict | None:
    """Rebuild a schema-style JSON object from normalized validation_rule rows.

    Returns a dict shaped like ``{"schema": <name>, "entities": {...}}`` so
    existing loader/query code can continue to operate on the same interface.
    """
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            "SELECT schema_id FROM ifc_schema WHERE version_name = %s LIMIT 1",
            (schema_name,),
        )
        schema_row = cur.fetchone()
        if not schema_row:
            return None
        schema_id = schema_row["schema_id"]

        cur.execute(
            """
            SELECT target_ifc_class, rule_schema
            FROM validation_rule
            WHERE schema_id = %s
              AND project_id IS NULL
              AND is_active = TRUE
            """,
            (schema_id,),
        )
        rows = [dict(r) for r in cur.fetchall()]

    entities: dict[str, dict] = {}
    for row in rows:
        payload = row.get("rule_schema")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
        if not isinstance(payload, dict):
            continue

        # Backward compatibility for legacy single-row payloads.
        if isinstance(payload.get("entities"), dict):
            return payload

        rule_type = payload.get("ruleType")
        entity_name = payload.get("entity") or row.get("target_ifc_class")
        if not entity_name:
            continue

        entity = entities.setdefault(
            entity_name,
            {"abstract": False, "parent": None, "attributes": []},
        )
        if rule_type == "inheritance":
            entity["parent"] = payload.get("parent")
            entity["abstract"] = bool(payload.get("abstract", False))
        elif rule_type == "required_attributes":
            declared = payload.get("declaredAttributes") or []
            if isinstance(declared, list):
                entity["attributes"] = declared

    if not entities:
        return None
    return {"schema": schema_name, "entities": entities}


def validation_schema_exists(schema_name: str) -> bool:
    """Return True if an IFC schema version already exists."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT 1 FROM ifc_schema WHERE version_name = %s LIMIT 1",
            (schema_name,),
        )
        return cur.fetchone() is not None


def insert_validation_rules(schema_name: str, rules: dict) -> None:
    """Insert normalized validation rules per entity for a schema version.

    This creates:
      1) one row in ``ifc_schema`` for ``schema_name``
      2) multiple rows in ``validation_rule`` (at least inheritance + required)
         per entity.
    """
    entities = rules.get("entities")
    if not isinstance(entities, dict) or not entities:
        raise ValueError("Schema JSON must include a non-empty 'entities' object")

    # Use a stable local UUID to avoid relying on DB default UUID generators.
    schema_id = str(uuid4())

    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO ifc_schema (schema_id, version_name) VALUES (%s, %s)",
            (schema_id, schema_name),
        )

        def lineage_for(entity_name: str) -> list[str]:
            lineage: list[str] = []
            seen: set[str] = set()
            current: str | None = entity_name
            while current:
                if current in seen:
                    break
                seen.add(current)
                lineage.append(current)
                parent = (entities.get(current) or {}).get("parent")
                current = parent if isinstance(parent, str) and parent else None
            lineage.reverse()  # root -> leaf
            return lineage

        def effective_required_attrs(entity_name: str) -> list[dict]:
            out: list[dict] = []
            for cls in lineage_for(entity_name):
                attrs = (entities.get(cls) or {}).get("attributes") or []
                if not isinstance(attrs, list):
                    continue
                for attr in attrs:
                    if not isinstance(attr, dict):
                        continue
                    if not bool(attr.get("required", False)):
                        continue
                    out.append(
                        {
                            "name": attr.get("name"),
                            "type": attr.get("type"),
                            "required": True,
                            "definedOn": cls,
                        }
                    )
            return out

        for entity_name, raw_meta in entities.items():
            meta = raw_meta if isinstance(raw_meta, dict) else {}
            parent = meta.get("parent")
            abstract = bool(meta.get("abstract", False))
            declared_attrs = meta.get("attributes") or []
            if not isinstance(declared_attrs, list):
                declared_attrs = []

            inheritance_rule = {
                "schema": schema_name,
                "ruleType": "inheritance",
                "entity": entity_name,
                "parent": parent if isinstance(parent, str) and parent else None,
                "abstract": abstract,
            }
            cur.execute(
                """
                INSERT INTO validation_rule (
                    name, description, schema_id, project_id, target_ifc_class,
                    rule_schema, severity, is_active
                )
                VALUES (%s, %s, %s, NULL, %s, %s, 'Info', TRUE)
                """,
                (
                    f"Inheritance: {entity_name}",
                    f"Inheritance rule for {entity_name} in {schema_name}",
                    schema_id,
                    entity_name,
                    json.dumps(inheritance_rule),
                ),
            )

            required_rule = {
                "schema": schema_name,
                "ruleType": "required_attributes",
                "entity": entity_name,
                "lineage": lineage_for(entity_name),
                "declaredAttributes": declared_attrs,
                "effectiveRequiredAttributes": effective_required_attrs(entity_name),
            }
            cur.execute(
                """
                INSERT INTO validation_rule (
                    name, description, schema_id, project_id, target_ifc_class,
                    rule_schema, severity, is_active
                )
                VALUES (%s, %s, %s, NULL, %s, %s, 'Error', TRUE)
                """,
                (
                    f"Required attributes: {entity_name}",
                    f"Required-attributes rule for {entity_name} in {schema_name}",
                    schema_id,
                    entity_name,
                    json.dumps(required_rule),
                ),
            )


def delete_ifc_schema_with_rules(schema_name: str) -> dict | None:
    """Delete an IFC schema and all attached validation_rule rows.

    Returns a dict with deletion counts, or ``None`` if the schema does not
    exist.
    """
    with get_cursor() as cur:
        cur.execute(
            "SELECT schema_id FROM ifc_schema WHERE version_name = %s LIMIT 1",
            (schema_name,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        schema_id = row[0]

        # Delete validation_rule rows first (FK references ifc_schema).
        # Use subquery to avoid type/format mismatch between Python and PG UUID.
        cur.execute(
            """
            DELETE FROM validation_rule
            WHERE schema_id = (SELECT schema_id FROM ifc_schema WHERE version_name = %s)
            """,
            (schema_name,),
        )
        deleted_rules = cur.rowcount

        cur.execute(
            "DELETE FROM ifc_schema WHERE version_name = %s",
            (schema_name,),
        )
        deleted_schemas = cur.rowcount

    return {
        "schema": schema_name,
        "schema_id": str(schema_id),
        "deleted_validation_rules": deleted_rules,
        "deleted_ifc_schemas": deleted_schemas,
    }


# ---------------------------------------------------------------------------
# Agent CRUD (IfcAgent as ifc_entity)
# ---------------------------------------------------------------------------
# Agents are stored as ifc_entity rows with ifc_class='IfcAgent'. Attributes
# {name, provider, model, api_key, base_url} live in the attributes JSONB.
# Stored on the project's main branch for project-scoped access.

IFC_AGENT_CLASS = "IfcAgent"


def _agent_content_hash(attrs: dict) -> str:
    """SHA-256 of attributes for SCD Type 2 change detection."""
    h = hashlib.sha256()
    h.update(json.dumps(attrs or {}, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return h.hexdigest()


def _agent_attrs(
    name: str,
    provider: str,
    model: str,
    api_key: str,
    base_url: str | None,
    pre_prompt: str | None = None,
) -> dict:
    return {
        "name": name,
        "provider": provider,
        "model": model,
        "api_key": api_key or "",
        "base_url": base_url or "",
        "pre_prompt": pre_prompt or "",
    }


def _row_to_agent(row: dict, project_id: str) -> dict:
    """Convert ifc_entity row to agent config dict (API shape)."""
    attrs = row.get("attributes") or {}
    if isinstance(attrs, str):
        attrs = json.loads(attrs)
    return {
        "entity_id": str(row["entity_id"]),
        "project_id": project_id,
        "name": attrs.get("name", ""),
        "provider": attrs.get("provider", ""),
        "model": attrs.get("model", ""),
        "api_key": attrs.get("api_key", ""),
        "base_url": attrs.get("base_url") or None,
        "pre_prompt": attrs.get("pre_prompt", ""),
    }


def create_agent_config(
    project_id: str, name: str, provider: str, model: str,
    api_key: str = "", base_url: str | None = None, pre_prompt: str | None = None,
) -> dict:
    """Create an IfcAgent entity on the project's main branch."""
    branches = fetch_branches(project_id)
    if not branches:
        raise ValueError(f"Project {project_id} has no branches")
    branch = branches[0]
    branch_id = str(branch["branch_id"])

    attrs = _agent_attrs(name, provider, model, api_key, base_url, pre_prompt)
    content_hash = _agent_content_hash(attrs)
    ifc_global_id = f"agent_{uuid4().hex[:20]}"

    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            "INSERT INTO revision (branch_id, ifc_filename, commit_message) "
            "VALUES (%s, %s, %s) RETURNING revision_id",
            (branch_id, "agent_config", f"IfcAgent: {name}"),
        )
        revision_id = cur.fetchone()["revision_id"]
        cur.execute(
            "INSERT INTO ifc_entity "
            "(branch_id, ifc_global_id, ifc_class, attributes, content_hash, created_in_revision_id) "
            "VALUES (%s, %s, %s, %s, %s, %s) RETURNING entity_id, attributes",
            (
                branch_id,
                ifc_global_id,
                IFC_AGENT_CLASS,
                psycopg2.extras.Json(attrs),
                content_hash,
                revision_id,
            ),
        )
        row = cur.fetchone()
    return _row_to_agent(dict(row), project_id)


def fetch_agent_configs_for_project(project_id: str) -> list[dict]:
    """List active IfcAgent entities for a project (from its main branch)."""
    branches = fetch_branches(project_id)
    if not branches:
        return []
    branch_id = str(branches[0]["branch_id"])

    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            "SELECT e.entity_id, e.attributes, r_cr.created_at "
            "FROM ifc_entity e "
            "JOIN revision r_cr ON e.created_in_revision_id = r_cr.revision_id "
            "WHERE e.branch_id = %s AND e.ifc_class = %s AND e.obsoleted_in_revision_id IS NULL "
            "ORDER BY r_cr.created_at DESC",
            (branch_id, IFC_AGENT_CLASS),
        )
        rows = cur.fetchall()
    return [_row_to_agent(dict(r), project_id) for r in rows]


def fetch_agent_config(entity_id: str) -> dict | None:
    """Fetch a single IfcAgent by entity_id."""
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            "SELECT e.entity_id, e.branch_id, e.attributes "
            "FROM ifc_entity e "
            "WHERE e.entity_id = %s AND e.ifc_class = %s AND e.obsoleted_in_revision_id IS NULL",
            (entity_id, IFC_AGENT_CLASS),
        )
        row = cur.fetchone()
    if not row:
        return None
    branch = fetch_branch(str(row["branch_id"]))
    project_id = str(branch["project_id"]) if branch else ""
    return _row_to_agent(dict(row), project_id)


def update_agent_config(
    entity_id: str, *, name: str | None = None, provider: str | None = None,
    model: str | None = None, api_key: str | None = None, base_url: str | None = None,
    pre_prompt: str | None = None,
) -> dict | None:
    """Update an IfcAgent by closing the old row and inserting a new one (SCD Type 2)."""
    existing = fetch_agent_config(entity_id)
    if not existing:
        return None

    attrs = _agent_attrs(
        name if name is not None else existing["name"],
        provider if provider is not None else existing["provider"],
        model if model is not None else existing["model"],
        api_key if api_key is not None else existing["api_key"],
        base_url if base_url is not None else existing["base_url"],
        pre_prompt if pre_prompt is not None else existing.get("pre_prompt"),
    )
    content_hash = _agent_content_hash(attrs)

    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            "SELECT branch_id, ifc_global_id FROM ifc_entity "
            "WHERE entity_id = %s AND obsoleted_in_revision_id IS NULL",
            (entity_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    branch_id = str(row["branch_id"])
    ifc_global_id = row["ifc_global_id"]

    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            "INSERT INTO revision (branch_id, ifc_filename, commit_message) "
            "VALUES (%s, %s, %s) RETURNING revision_id",
            (branch_id, "agent_config", f"IfcAgent update: {attrs['name']}"),
        )
        revision_id = cur.fetchone()["revision_id"]
        cur.execute(
            "UPDATE ifc_entity SET obsoleted_in_revision_id = %s "
            "WHERE entity_id = %s AND obsoleted_in_revision_id IS NULL",
            (revision_id, entity_id),
        )
        cur.execute(
            "INSERT INTO ifc_entity "
            "(branch_id, ifc_global_id, ifc_class, attributes, content_hash, created_in_revision_id) "
            "VALUES (%s, %s, %s, %s, %s, %s) RETURNING entity_id, attributes",
            (
                branch_id,
                ifc_global_id,
                IFC_AGENT_CLASS,
                psycopg2.extras.Json(attrs),
                content_hash,
                revision_id,
            ),
        )
        new_row = cur.fetchone()
    branch = fetch_branch(branch_id)
    project_id = str(branch["project_id"]) if branch else ""
    return _row_to_agent(dict(new_row), project_id)


def delete_agent_config(entity_id: str) -> bool:
    """Obsolete an IfcAgent entity (SCD Type 2 close)."""
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            "SELECT branch_id FROM ifc_entity "
            "WHERE entity_id = %s AND ifc_class = %s AND obsoleted_in_revision_id IS NULL",
            (entity_id, IFC_AGENT_CLASS),
        )
        row = cur.fetchone()
    if not row:
        return False

    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            "INSERT INTO revision (branch_id, ifc_filename, commit_message) "
            "VALUES (%s, %s, %s) RETURNING revision_id",
            (str(row["branch_id"]), "agent_config", "IfcAgent delete"),
        )
        revision_id = cur.fetchone()["revision_id"]
        cur.execute(
            "UPDATE ifc_entity SET obsoleted_in_revision_id = %s "
            "WHERE entity_id = %s AND obsoleted_in_revision_id IS NULL",
            (revision_id, entity_id),
        )
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Agent chat CRUD (persistent conversation history)
# ---------------------------------------------------------------------------

_CHAT_COLS = "chat_id, project_id, branch_id, title, created_at, updated_at"
_MSG_COLS = "message_id, chat_id, role, content, tool_calls, created_at"


def create_agent_chat(project_id: str, branch_id: str, title: str = "New chat") -> dict:
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            f"INSERT INTO agent_chat (project_id, branch_id, title) "
            f"VALUES (%s, %s, %s) RETURNING {_CHAT_COLS}",
            (project_id, branch_id, title),
        )
        return dict(cur.fetchone())


def fetch_agent_chats(project_id: str, branch_id: str | None = None) -> list[dict]:
    with get_cursor(dict_cursor=True) as cur:
        if branch_id:
            cur.execute(
                f"SELECT {_CHAT_COLS} FROM agent_chat "
                f"WHERE project_id = %s AND branch_id = %s ORDER BY updated_at DESC",
                (project_id, branch_id),
            )
        else:
            cur.execute(
                f"SELECT {_CHAT_COLS} FROM agent_chat "
                f"WHERE project_id = %s ORDER BY updated_at DESC",
                (project_id,),
            )
        return [dict(r) for r in cur.fetchall()]


def update_agent_chat(chat_id: str, title: str) -> dict | None:
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            f"UPDATE agent_chat SET title = %s, updated_at = now() "
            f"WHERE chat_id = %s RETURNING {_CHAT_COLS}",
            (title, chat_id),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def delete_agent_chat(chat_id: str) -> bool:
    with get_cursor() as cur:
        cur.execute("DELETE FROM agent_chat WHERE chat_id = %s", (chat_id,))
        return cur.rowcount > 0


def add_chat_message(
    chat_id: str, role: str, content: str, tool_calls: list[dict] | None = None,
) -> dict:
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            f"INSERT INTO agent_chat_message (chat_id, role, content, tool_calls) "
            f"VALUES (%s, %s, %s, %s) RETURNING {_MSG_COLS}",
            (chat_id, role, content, json.dumps(tool_calls) if tool_calls else None),
        )
        row = dict(cur.fetchone())
        cur.execute(
            "UPDATE agent_chat SET updated_at = now() WHERE chat_id = %s",
            (chat_id,),
        )
        return row


def fetch_chat_messages(chat_id: str) -> list[dict]:
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            f"SELECT {_MSG_COLS} FROM agent_chat_message "
            f"WHERE chat_id = %s ORDER BY created_at ASC",
            (chat_id,),
        )
        rows = [dict(r) for r in cur.fetchall()]
        for r in rows:
            if isinstance(r.get("tool_calls"), str):
                r["tool_calls"] = json.loads(r["tool_calls"])
        return rows
