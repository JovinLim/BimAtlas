"""Postgres/AGE connection pool (psycopg2) and relational query helpers.

Provides a threaded connection pool, a cursor context-manager that handles
commit/rollback, and revision-scoped query functions for the SCD Type 2
``ifc_products`` table and the ``revisions`` table.
"""

from __future__ import annotations

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
    return _pool.getconn()


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
# Revision helpers
# ---------------------------------------------------------------------------


def get_latest_revision_id() -> int | None:
    """Return the most recent revision id, or ``None`` if no revisions exist."""
    with get_cursor() as cur:
        cur.execute("SELECT MAX(id) FROM revisions")
        row = cur.fetchone()
        return row[0] if row else None


def fetch_revisions() -> list[dict]:
    """Return all revisions ordered by id ascending."""
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            "SELECT id, label, ifc_filename, created_at "
            "FROM revisions ORDER BY id ASC"
        )
        return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Product queries -- revision-scoped (SCD Type 2)
# ---------------------------------------------------------------------------

_PRODUCT_COLS = (
    "global_id, ifc_class, name, description, object_type, tag, "
    "contained_in, vertices, normals, faces, matrix"
)

_REV_FILTER = "valid_from_rev <= %s AND (valid_to_rev IS NULL OR valid_to_rev > %s)"


def fetch_product_at_revision(global_id: str, rev: int) -> dict | None:
    """Fetch a single product visible at *rev*."""
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(
            f"SELECT {_PRODUCT_COLS} FROM ifc_products "
            f"WHERE global_id = %s AND {_REV_FILTER} LIMIT 1",
            (global_id, rev, rev),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def fetch_products_at_revision(
    rev: int,
    ifc_class: str | None = None,
    contained_in: str | None = None,
) -> list[dict]:
    """List products visible at *rev*, optionally filtered by class or container."""
    clauses: list[str] = [_REV_FILTER]
    params: list = [rev, rev]

    if ifc_class is not None:
        clauses.append("ifc_class = %s")
        params.append(ifc_class)
    if contained_in is not None:
        clauses.append("contained_in = %s")
        params.append(contained_in)

    where = " AND ".join(clauses)
    with get_cursor(dict_cursor=True) as cur:
        cur.execute(f"SELECT {_PRODUCT_COLS} FROM ifc_products WHERE {where}", params)
        return [dict(r) for r in cur.fetchall()]


def fetch_spatial_container(contained_in_gid: str | None, rev: int) -> dict | None:
    """Fetch the spatial container for an element (by contained_in GlobalId)."""
    if not contained_in_gid:
        return None
    return fetch_product_at_revision(contained_in_gid, rev)


# ---------------------------------------------------------------------------
# Revision diff -- state comparison between two revisions
# ---------------------------------------------------------------------------


def fetch_revision_diff(from_rev: int, to_rev: int) -> dict:
    """Compare visible products between *from_rev* and *to_rev*.

    Returns ``{"added": [...], "modified": [...], "deleted": [...]}`` where
    each element is a dict with ``global_id``, ``ifc_class``, ``name``.
    """
    with get_cursor(dict_cursor=True) as cur:
        # Added: visible at to_rev but not at from_rev
        cur.execute(
            "SELECT t.global_id, t.ifc_class, t.name "
            "FROM ifc_products t "
            "WHERE t.valid_from_rev <= %s "
            "  AND (t.valid_to_rev IS NULL OR t.valid_to_rev > %s) "
            "  AND NOT EXISTS ("
            "      SELECT 1 FROM ifc_products f "
            "      WHERE f.global_id = t.global_id "
            "        AND f.valid_from_rev <= %s "
            "        AND (f.valid_to_rev IS NULL OR f.valid_to_rev > %s)"
            "  )",
            (to_rev, to_rev, from_rev, from_rev),
        )
        added = [dict(r) for r in cur.fetchall()]

        # Deleted: visible at from_rev but not at to_rev
        cur.execute(
            "SELECT f.global_id, f.ifc_class, f.name "
            "FROM ifc_products f "
            "WHERE f.valid_from_rev <= %s "
            "  AND (f.valid_to_rev IS NULL OR f.valid_to_rev > %s) "
            "  AND NOT EXISTS ("
            "      SELECT 1 FROM ifc_products t "
            "      WHERE t.global_id = f.global_id "
            "        AND t.valid_from_rev <= %s "
            "        AND (t.valid_to_rev IS NULL OR t.valid_to_rev > %s)"
            "  )",
            (from_rev, from_rev, to_rev, to_rev),
        )
        deleted = [dict(r) for r in cur.fetchall()]

        # Modified: visible at both but with different content_hash
        cur.execute(
            "SELECT t.global_id, t.ifc_class, t.name "
            "FROM ifc_products t "
            "JOIN ifc_products f ON t.global_id = f.global_id "
            "WHERE t.valid_from_rev <= %s "
            "  AND (t.valid_to_rev IS NULL OR t.valid_to_rev > %s) "
            "  AND f.valid_from_rev <= %s "
            "  AND (f.valid_to_rev IS NULL OR f.valid_to_rev > %s) "
            "  AND t.content_hash != f.content_hash",
            (to_rev, to_rev, from_rev, from_rev),
        )
        modified = [dict(r) for r in cur.fetchall()]

    return {"added": added, "modified": modified, "deleted": deleted}
