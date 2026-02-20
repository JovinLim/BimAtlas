"""Postgres/AGE connection pool (psycopg2) and relational query helpers.

Provides a threaded connection pool, a cursor context-manager that handles
commit/rollback, and revision-scoped query functions for the SCD Type 2
``ifc_products`` table, the ``revisions`` table, the ``projects`` /
``branches`` tables, and the ``filter_sets`` / ``branch_applied_filter_sets``
tables.
"""

from __future__ import annotations

import json
from contextlib import contextmanager

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
            "INSERT INTO projects (name, description) VALUES (%s, %s) RETURNING id, name, description, created_at",
            (name, description),
        )
        project = dict(cur.fetchone())

        # Auto-create the default "main" branch
        cur.execute(
            "INSERT INTO branches (project_id, name) VALUES (%s, 'main') RETURNING id, project_id, name, created_at",
            (project["id"],),
        )
    return project


def fetch_projects() -> list[dict]:
    """Return all projects ordered by created_at descending."""
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            "SELECT id, name, description, created_at FROM projects ORDER BY created_at DESC"
        )
        return [dict(r) for r in cur.fetchall()]


def fetch_project(project_id: int) -> dict | None:
    """Return a single project by id."""
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            "SELECT id, name, description, created_at FROM projects WHERE id = %s",
            (project_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# Branch helpers
# ---------------------------------------------------------------------------


def create_branch(project_id: int, name: str) -> dict:
    """Create a new branch within a project. Returns the branch dict."""
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            "INSERT INTO branches (project_id, name) VALUES (%s, %s) RETURNING id, project_id, name, created_at",
            (project_id, name),
        )
        return dict(cur.fetchone())


def fetch_branches(project_id: int) -> list[dict]:
    """Return all branches for a project, ordered by created_at."""
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            "SELECT id, project_id, name, created_at FROM branches WHERE project_id = %s ORDER BY created_at ASC",
            (project_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def fetch_branch(branch_id: int) -> dict | None:
    """Return a single branch by id."""
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            "SELECT id, project_id, name, created_at FROM branches WHERE id = %s",
            (branch_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def fetch_branch_by_name(project_id: int, name: str) -> dict | None:
    """Return a branch by project_id and name."""
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            "SELECT id, project_id, name, created_at FROM branches WHERE project_id = %s AND name = %s",
            (project_id, name),
        )
        row = cur.fetchone()
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# Revision helpers (scoped to branch)
# ---------------------------------------------------------------------------


def get_latest_revision_id(branch_id: int) -> int | None:
    """Return the most recent revision id for a branch, or ``None`` if none exist."""
    with get_cursor() as cur:
        cur.execute("SELECT MAX(id) FROM revisions WHERE branch_id = %s", (branch_id,))
        row = cur.fetchone()
        return row[0] if row else None


def fetch_revisions(branch_id: int) -> list[dict]:
    """Return all revisions for a branch, ordered by id ascending."""
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            "SELECT id, branch_id, label, ifc_filename, created_at "
            "FROM revisions WHERE branch_id = %s ORDER BY id ASC",
            (branch_id,),
        )
        return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Product queries -- branch + revision scoped (SCD Type 2)
# ---------------------------------------------------------------------------

_PRODUCT_COLS = (
    "global_id, ifc_class, name, description, object_type, tag, "
    "contained_in, vertices, normals, faces, matrix"
)

_REV_FILTER = "valid_from_rev <= %s AND (valid_to_rev IS NULL OR valid_to_rev > %s)"


def fetch_product_at_revision(global_id: str, rev: int, branch_id: int) -> dict | None:
    """Fetch a single product visible at *rev* on *branch_id*."""
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            f"SELECT {_PRODUCT_COLS} FROM ifc_products "
            f"WHERE global_id = %s AND branch_id = %s AND {_REV_FILTER} LIMIT 1",
            (global_id, branch_id, rev, rev),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def fetch_products_at_revision(
    rev: int,
    branch_id: int,
    ifc_class: str | None = None,
    ifc_classes: list[str] | None = None,
    contained_in: str | None = None,
    name: str | None = None,
    object_type: str | None = None,
    tag: str | None = None,
    description: str | None = None,
    global_id: str | None = None,
) -> list[dict]:
    """List products visible at *rev* on *branch_id*, optionally filtered."""
    clauses: list[str] = ["branch_id = %s", _REV_FILTER]
    params: list = [branch_id, rev, rev]

    if ifc_classes is not None and len(ifc_classes) > 0:
        clauses.append("ifc_class = ANY(%s)")
        params.append(ifc_classes)
    elif ifc_class is not None:
        clauses.append("ifc_class = %s")
        params.append(ifc_class)
    if contained_in is not None:
        clauses.append("contained_in = %s")
        params.append(contained_in)
    if name is not None:
        clauses.append("name ILIKE %s")
        params.append(f"%{name}%")
    if object_type is not None:
        clauses.append("object_type ILIKE %s")
        params.append(f"%{object_type}%")
    if tag is not None:
        clauses.append("tag ILIKE %s")
        params.append(f"%{tag}%")
    if description is not None:
        clauses.append("description ILIKE %s")
        params.append(f"%{description}%")
    if global_id is not None:
        clauses.append("global_id ILIKE %s")
        params.append(f"%{global_id}%")

    where = " AND ".join(clauses)
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(f"SELECT {_PRODUCT_COLS} FROM ifc_products WHERE {where}", params)
        return [dict(r) for r in cur.fetchall()]


def fetch_spatial_container(contained_in_gid: str | None, rev: int, branch_id: int) -> dict | None:
    """Fetch the spatial container for an element (by contained_in GlobalId)."""
    if not contained_in_gid:
        return None
    return fetch_product_at_revision(contained_in_gid, rev, branch_id)


# ---------------------------------------------------------------------------
# Revision diff -- state comparison between two revisions (same branch)
# ---------------------------------------------------------------------------


def fetch_revision_diff(from_rev: int, to_rev: int, branch_id: int) -> dict:
    """Compare visible products between *from_rev* and *to_rev* on a branch.

    Returns ``{"added": [...], "modified": [...], "deleted": [...]}`` where
    each element is a dict with ``global_id``, ``ifc_class``, ``name``.
    """
    with get_cursor(dict_cursor=True) as cur:
        # Added: visible at to_rev but not at from_rev
        cur.execute(
            "SELECT t.global_id, t.ifc_class, t.name "
            "FROM ifc_products t "
            "WHERE t.branch_id = %s "
            "  AND t.valid_from_rev <= %s "
            "  AND (t.valid_to_rev IS NULL OR t.valid_to_rev > %s) "
            "  AND NOT EXISTS ("
            "      SELECT 1 FROM ifc_products f "
            "      WHERE f.branch_id = %s "
            "        AND f.global_id = t.global_id "
            "        AND f.valid_from_rev <= %s "
            "        AND (f.valid_to_rev IS NULL OR f.valid_to_rev > %s)"
            "  )",
            (branch_id, to_rev, to_rev, branch_id, from_rev, from_rev),
        )
        added = [dict(r) for r in cur.fetchall()]

        # Deleted: visible at from_rev but not at to_rev
        cur.execute(
            "SELECT f.global_id, f.ifc_class, f.name "
            "FROM ifc_products f "
            "WHERE f.branch_id = %s "
            "  AND f.valid_from_rev <= %s "
            "  AND (f.valid_to_rev IS NULL OR f.valid_to_rev > %s) "
            "  AND NOT EXISTS ("
            "      SELECT 1 FROM ifc_products t "
            "      WHERE t.branch_id = %s "
            "        AND t.global_id = f.global_id "
            "        AND t.valid_from_rev <= %s "
            "        AND (t.valid_to_rev IS NULL OR t.valid_to_rev > %s)"
            "  )",
            (branch_id, from_rev, from_rev, branch_id, to_rev, to_rev),
        )
        deleted = [dict(r) for r in cur.fetchall()]

        # Modified: visible at both but with different content_hash
        cur.execute(
            "SELECT t.global_id, t.ifc_class, t.name "
            "FROM ifc_products t "
            "JOIN ifc_products f ON t.global_id = f.global_id "
            "WHERE t.branch_id = %s AND f.branch_id = %s "
            "  AND t.valid_from_rev <= %s "
            "  AND (t.valid_to_rev IS NULL OR t.valid_to_rev > %s) "
            "  AND f.valid_from_rev <= %s "
            "  AND (f.valid_to_rev IS NULL OR f.valid_to_rev > %s) "
            "  AND t.content_hash != f.content_hash",
            (branch_id, branch_id, to_rev, to_rev, from_rev, from_rev),
        )
        modified = [dict(r) for r in cur.fetchall()]

    return {"added": added, "modified": modified, "deleted": deleted}


# ---------------------------------------------------------------------------
# Filter set CRUD
# ---------------------------------------------------------------------------

_FILTER_SET_COLS = "id, branch_id, name, logic, filters, created_at, updated_at"


def create_filter_set(
    branch_id: int, name: str, logic: str, filters_json: list[dict],
) -> dict:
    """Create a new filter set on a branch. Returns the new row."""
    # #region agent log
    _log_path = "/home/jovin/projects/BimAtlas/.cursor/debug-69dfaf.log"
    import time as _time
    _ts = int(_time.time() * 1000)
    try:
        with open(_log_path, "a") as _f:
            _f.write(
                '{"sessionId":"69dfaf","id":"log_create_fs_entry","timestamp":%d,"location":"db.py:create_filter_set","message":"create_filter_set entry","data":{"branch_id":%s,"name":"%s"},"hypothesisId":"A"}\n'
                % (_ts, branch_id, name.replace('"', '\\"'))
            )
    except Exception:
        pass
    # #endregion
    try:
        with get_cursor(dict_cursor=True) as cur:
            cur.execute(
                f"INSERT INTO filter_sets (branch_id, name, logic, filters) "
                f"VALUES (%s, %s, %s, %s) RETURNING {_FILTER_SET_COLS}",
                (branch_id, name, logic, json.dumps(filters_json)),
            )
            return dict(cur.fetchone())
    except Exception as e:  # #region agent log
        try:
            with open(_log_path, "a") as _f:
                _f.write(
                    '{"sessionId":"69dfaf","id":"log_create_fs_err","timestamp":%d,"location":"db.py:create_filter_set","message":"create_filter_set exception","data":{"error":"%s"},"hypothesisId":"A"}\n'
                    % (int(_time.time() * 1000), str(e).replace('"', '\\"').replace("\n", " "))
                )
        except Exception:
            pass
        raise  # #endregion


def update_filter_set(
    filter_set_id: int,
    name: str | None = None,
    logic: str | None = None,
    filters_json: list[dict] | None = None,
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
    params.append(filter_set_id)
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            f"UPDATE filter_sets SET {', '.join(sets)} WHERE id = %s "
            f"RETURNING {_FILTER_SET_COLS}",
            params,
        )
        row = cur.fetchone()
        return dict(row) if row else None


def delete_filter_set(filter_set_id: int) -> bool:
    """Delete a filter set by id. Returns True if a row was deleted."""
    with get_cursor() as cur:
        cur.execute("DELETE FROM filter_sets WHERE id = %s", (filter_set_id,))
        return cur.rowcount > 0


def fetch_filter_set(filter_set_id: int) -> dict | None:
    """Fetch a single filter set by id."""
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            f"SELECT {_FILTER_SET_COLS} FROM filter_sets WHERE id = %s",
            (filter_set_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def fetch_filter_sets_for_branch(branch_id: int) -> list[dict]:
    """Return all filter sets for a branch, newest first."""
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            f"SELECT {_FILTER_SET_COLS} FROM filter_sets "
            f"WHERE branch_id = %s ORDER BY updated_at DESC",
            (branch_id,),
        )
        return [dict(r) for r in cur.fetchall()]


def search_filter_sets(
    query: str,
    branch_id: int | None = None,
    project_id: int | None = None,
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
    join = "JOIN branches b ON fs.branch_id = b.id" if needs_join else ""
    where = " AND ".join(clauses)

    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            f"SELECT fs.id, fs.branch_id, fs.name, fs.logic, fs.filters, "
            f"fs.created_at, fs.updated_at "
            f"FROM filter_sets fs {join} WHERE {where} ORDER BY fs.updated_at DESC",
            params,
        )
        return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Applied filter sets (tracks active filter sets per branch)
# ---------------------------------------------------------------------------


def apply_filter_sets(
    branch_id: int, filter_set_ids: list[int], combination_logic: str,
) -> None:
    """Replace the applied filter sets for a branch."""
    with get_cursor() as cur:
        cur.execute(
            "DELETE FROM branch_applied_filter_sets WHERE branch_id = %s",
            (branch_id,),
        )
        for fs_id in filter_set_ids:
            cur.execute(
                "INSERT INTO branch_applied_filter_sets "
                "(branch_id, filter_set_id, combination_logic) VALUES (%s, %s, %s)",
                (branch_id, fs_id, combination_logic),
            )


def fetch_applied_filter_sets(branch_id: int) -> dict:
    """Return the currently applied filter sets for a branch.

    Returns ``{"filter_sets": [...], "combination_logic": "AND"|"OR"}``.
    """
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            "SELECT ba.combination_logic, ba.filter_set_id, "
            f"fs.id, fs.branch_id, fs.name, fs.logic, fs.filters, "
            f"fs.created_at, fs.updated_at "
            "FROM branch_applied_filter_sets ba "
            "JOIN filter_sets fs ON ba.filter_set_id = fs.id "
            "WHERE ba.branch_id = %s ORDER BY ba.applied_at ASC",
            (branch_id,),
        )
        rows = [dict(r) for r in cur.fetchall()]

    if not rows:
        return {"filter_sets": [], "combination_logic": "AND"}

    combination_logic = rows[0]["combination_logic"]
    filter_sets = [
        {
            "id": r["id"],
            "branch_id": r["branch_id"],
            "name": r["name"],
            "logic": r["logic"],
            "filters": r["filters"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]
    return {"filter_sets": filter_sets, "combination_logic": combination_logic}


# ---------------------------------------------------------------------------
# Product filtering with structured filter sets
# ---------------------------------------------------------------------------


def _build_filter_clause(f: dict, params: list) -> str | None:
    """Convert a single filter dict into a SQL clause, appending bind params."""
    mode = f.get("mode")
    if mode == "class":
        ifc_class = f.get("ifcClass") or f.get("ifc_class")
        if ifc_class:
            params.append(ifc_class)
            return "ifc_class = %s"
    elif mode == "attribute":
        attr = f.get("attribute")
        value = f.get("value")
        col_map = {
            "globalId": "global_id",
            "name": "name",
            "objectType": "object_type",
            "tag": "tag",
            "description": "description",
        }
        col = col_map.get(attr, attr) if attr else None
        if col and value:
            params.append(f"%{value}%")
            return f"{col} ILIKE %s"
    return None


def fetch_products_with_filter_sets(
    rev: int,
    branch_id: int,
    filter_sets_data: list[dict],
    combination_logic: str = "AND",
) -> list[dict]:
    """Query products matching multiple filter sets with configurable logic.

    Each entry in *filter_sets_data* has keys ``logic`` (``"AND"``/``"OR"``)
    and ``filters`` (list of filter dicts).  Conditions within a set are
    joined by the set's ``logic``; the resulting groups are joined by
    *combination_logic*.
    """
    base_clauses: list[str] = ["branch_id = %s", _REV_FILTER]
    params: list = [branch_id, rev, rev]

    group_sqls: list[str] = []
    for fs in filter_sets_data:
        fs_logic = fs.get("logic", "AND")
        filter_clauses: list[str] = []
        for f in fs.get("filters", []):
            clause = _build_filter_clause(f, params)
            if clause:
                filter_clauses.append(clause)
        if filter_clauses:
            joiner = f" {fs_logic} "
            group_sqls.append(f"({joiner.join(filter_clauses)})")

    if group_sqls:
        set_joiner = f" {combination_logic} "
        base_clauses.append(f"({set_joiner.join(group_sqls)})")

    where = " AND ".join(base_clauses)
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(f"SELECT {_PRODUCT_COLS} FROM ifc_products WHERE {where}", params)
        return [dict(r) for r in cur.fetchall()]
