"""Orchestrates IFC parse -> DB insert (versioned ingestion pipeline).

Implements the two-phase, diff-aware ingestion described in the plan:

  **Phase 1 -- Extract:** Open the IFC model once and extract:
    - All products (spatial structure + geometric elements) via :mod:`.geometry`
    - All IFC objectified relationships as directed ``(from, to, type)`` triples

  **Phase 2 -- Diff & Apply:** Compare new products against the current
  revision using ``content_hash`` (SHA-256 of all mutable fields), then:
    - Create a new ``revisions`` row
    - Close SCD Type 2 rows for modified/deleted products (``valid_to_rev``)
    - Insert new SCD Type 2 rows for added/modified products
    - Close graph nodes + edges for modified/deleted products
    - Create revision-tagged graph nodes for added/modified products
    - Create revision-tagged graph edges for relationships involving
      added/modified products (edges between unchanged products carry forward)

See the plan (Section 3b) for full details on the SCD Type 2 versioning
model, revision-tagged graph semantics, and the ``content_hash`` diff
algorithm.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import ifcopenshell
import psycopg2.extras

from ...db import get_conn, put_conn
from ..graph import age_client
from .geometry import IfcProductRecord, extract_products_from_model

logger = logging.getLogger("bimatlas.ingestion")


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class IfcRelationshipRecord:
    """A directed IFC objectified relationship to create as a graph edge.

    Edge direction follows IFC semantics:
      - ``IfcRelAggregates``: parent -> child
      - ``IfcRelContainedInSpatialStructure``: element -> spatial container
      - ``IfcRelVoidsElement``: building element -> opening element
      - ``IfcRelFillsElement``: opening element -> filling element
      - ``IfcRelConnectsElements``: relating element -> related element
    """

    from_global_id: str
    to_global_id: str
    relationship_type: str  # AGE edge label, e.g. "IfcRelAggregates"


@dataclass
class IngestionResult:
    """Summary of a completed ingestion run."""

    revision_id: int
    total_products: int
    added: int
    modified: int
    deleted: int
    unchanged: int
    edges_created: int


# ---------------------------------------------------------------------------
# Relationship extraction
# ---------------------------------------------------------------------------


def _extract_relationships(
    model: ifcopenshell.file,
) -> list[IfcRelationshipRecord]:
    """Extract IFC objectified relationships as directed triples.

    Parses the core IFC 4.3 relationship entities that form the spatial
    decomposition tree, containment, and element connectivity graph.

    Only relationships between entities that have a ``GlobalId`` are included
    (this covers all ``IfcRoot`` subtypes).
    """
    rels: list[IfcRelationshipRecord] = []

    # -- IfcRelAggregates: parent -> child (spatial decomposition) ----------
    for rel in model.by_type("IfcRelAggregates"):
        parent = rel.RelatingObject
        if parent is None:
            continue
        parent_gid = getattr(parent, "GlobalId", None)
        if not parent_gid:
            continue
        for child in rel.RelatedObjects or []:
            child_gid = getattr(child, "GlobalId", None)
            if child_gid:
                rels.append(
                    IfcRelationshipRecord(
                        from_global_id=parent_gid,
                        to_global_id=child_gid,
                        relationship_type="IfcRelAggregates",
                    )
                )

    # -- IfcRelContainedInSpatialStructure: element -> container ------------
    for rel in model.by_type("IfcRelContainedInSpatialStructure"):
        container = rel.RelatingStructure
        if container is None:
            continue
        container_gid = getattr(container, "GlobalId", None)
        if not container_gid:
            continue
        for element in rel.RelatedElements or []:
            elem_gid = getattr(element, "GlobalId", None)
            if elem_gid:
                rels.append(
                    IfcRelationshipRecord(
                        from_global_id=elem_gid,
                        to_global_id=container_gid,
                        relationship_type="IfcRelContainedInSpatialStructure",
                    )
                )

    # -- IfcRelVoidsElement: building element -> opening --------------------
    for rel in model.by_type("IfcRelVoidsElement"):
        building_elem = getattr(rel, "RelatingBuildingElement", None)
        opening_elem = getattr(rel, "RelatedOpeningElement", None)
        b_gid = getattr(building_elem, "GlobalId", None) if building_elem else None
        o_gid = getattr(opening_elem, "GlobalId", None) if opening_elem else None
        if b_gid and o_gid:
            rels.append(
                IfcRelationshipRecord(
                    from_global_id=b_gid,
                    to_global_id=o_gid,
                    relationship_type="IfcRelVoidsElement",
                )
            )

    # -- IfcRelFillsElement: opening -> filling element (door/window) -------
    for rel in model.by_type("IfcRelFillsElement"):
        opening = getattr(rel, "RelatingOpeningElement", None)
        filling = getattr(rel, "RelatedBuildingElement", None)
        op_gid = getattr(opening, "GlobalId", None) if opening else None
        fi_gid = getattr(filling, "GlobalId", None) if filling else None
        if op_gid and fi_gid:
            rels.append(
                IfcRelationshipRecord(
                    from_global_id=op_gid,
                    to_global_id=fi_gid,
                    relationship_type="IfcRelFillsElement",
                )
            )

    # -- IfcRelConnectsElements: relating -> related ------------------------
    for rel in model.by_type("IfcRelConnectsElements"):
        relating = getattr(rel, "RelatingElement", None)
        related = getattr(rel, "RelatedElement", None)
        r1_gid = getattr(relating, "GlobalId", None) if relating else None
        r2_gid = getattr(related, "GlobalId", None) if related else None
        if r1_gid and r2_gid:
            rels.append(
                IfcRelationshipRecord(
                    from_global_id=r1_gid,
                    to_global_id=r2_gid,
                    relationship_type="IfcRelConnectsElements",
                )
            )

    return rels


# ---------------------------------------------------------------------------
# Diff engine
# ---------------------------------------------------------------------------


def _diff_products(
    new_records: list[IfcProductRecord],
    current_hashes: dict[str, str],
) -> tuple[
    list[IfcProductRecord],  # added
    list[IfcProductRecord],  # modified
    set[str],  # deleted_gids
    set[str],  # unchanged_gids
]:
    """Diff new product records against the current revision's content hashes.

    Classification:
      - **Added**: ``global_id`` not present in *current_hashes*.
      - **Modified**: ``global_id`` present but ``content_hash`` differs.
      - **Deleted**: ``global_id`` in *current_hashes* but not in *new_records*.
      - **Unchanged**: same ``global_id`` and same ``content_hash``.
    """
    new_by_gid: dict[str, IfcProductRecord] = {r.global_id: r for r in new_records}
    new_gids = set(new_by_gid.keys())
    current_gids = set(current_hashes.keys())

    added_gids = new_gids - current_gids
    deleted_gids = current_gids - new_gids
    common_gids = new_gids & current_gids

    modified_gids: set[str] = set()
    unchanged_gids: set[str] = set()

    for gid in common_gids:
        if new_by_gid[gid].content_hash != current_hashes[gid]:
            modified_gids.add(gid)
        else:
            unchanged_gids.add(gid)

    added = [new_by_gid[gid] for gid in added_gids]
    modified = [new_by_gid[gid] for gid in modified_gids]

    return added, modified, deleted_gids, unchanged_gids


# ---------------------------------------------------------------------------
# Relational operations (single-transaction)
# ---------------------------------------------------------------------------


def _create_revision(
    cur,
    ifc_filename: str,
    label: str | None,
) -> int:
    """Insert a new revision row and return its id."""
    cur.execute(
        "INSERT INTO revisions (label, ifc_filename) VALUES (%s, %s) RETURNING id",
        (label, ifc_filename),
    )
    return cur.fetchone()[0]


def _load_current_hashes(cur) -> dict[str, str]:
    """Load ``global_id -> content_hash`` for all current (non-closed) products."""
    cur.execute(
        "SELECT global_id, content_hash FROM ifc_products WHERE valid_to_rev IS NULL"
    )
    return {row[0]: row[1] for row in cur.fetchall()}


def _close_product_rows(cur, global_ids: list[str], rev_id: int) -> None:
    """Close SCD Type 2 rows for the given global_ids (set ``valid_to_rev``)."""
    if not global_ids:
        return
    cur.execute(
        "UPDATE ifc_products SET valid_to_rev = %s "
        "WHERE global_id = ANY(%s) AND valid_to_rev IS NULL",
        (rev_id, global_ids),
    )


def _insert_product_rows(
    cur,
    records: list[IfcProductRecord],
    rev_id: int,
) -> None:
    """Batch-insert product rows for a revision using ``execute_values``."""
    if not records:
        return
    psycopg2.extras.execute_values(
        cur,
        "INSERT INTO ifc_products "
        "(global_id, ifc_class, name, description, object_type, tag, "
        "contained_in, vertices, normals, faces, matrix, "
        "content_hash, valid_from_rev) VALUES %s",
        [
            (
                r.global_id,
                r.ifc_class,
                r.name,
                r.description,
                r.object_type,
                r.tag,
                r.contained_in,
                psycopg2.Binary(r.vertices) if r.vertices else None,
                psycopg2.Binary(r.normals) if r.normals else None,
                psycopg2.Binary(r.faces) if r.faces else None,
                psycopg2.Binary(r.matrix) if r.matrix else None,
                r.content_hash,
                rev_id,
            )
            for r in records
        ],
    )


# ---------------------------------------------------------------------------
# Graph operations
# ---------------------------------------------------------------------------


def _close_graph_entities(changed_gids: set[str], rev_id: int) -> None:
    """Close graph nodes and their edges for modified/deleted products.

    Edges are closed **before** nodes so that the edge MATCH can still find
    the node by ``global_id`` (even though the node is about to be closed).
    """
    for gid in changed_gids:
        try:
            age_client.close_edges_for_node(gid, rev_id)
        except Exception as exc:
            logger.warning("Failed to close edges for node %s: %s", gid, exc)
        try:
            age_client.close_node(gid, rev_id)
        except Exception as exc:
            logger.warning("Failed to close graph node %s: %s", gid, exc)


def _create_graph_nodes(records: list[IfcProductRecord], rev_id: int) -> None:
    """Create revision-tagged graph nodes for added/modified products."""
    for record in records:
        try:
            age_client.create_node(
                ifc_class=record.ifc_class,
                global_id=record.global_id,
                name=record.name,
                rev_id=rev_id,
            )
        except Exception as exc:
            logger.warning(
                "Failed to create graph node %s (%s): %s",
                record.global_id,
                record.ifc_class,
                exc,
            )


def _create_graph_edges(
    relationships: list[IfcRelationshipRecord],
    changed_or_new_gids: set[str],
    all_new_gids: set[str],
    rev_id: int,
) -> int:
    """Create revision-tagged graph edges for relationships.

    Only edges where **at least one endpoint** is in *changed_or_new_gids*
    (added or modified products) are created.  Edges between two unchanged
    products carry forward from the previous revision automatically (they
    remain connected to the same node entities with ``valid_to_rev = -1``).

    Both endpoints must exist in *all_new_gids* (the new model) -- dangling
    edges are skipped.

    Returns the number of edges created.
    """
    created = 0
    for rel in relationships:
        # Only create edges involving at least one changed/new product
        if (
            rel.from_global_id not in changed_or_new_gids
            and rel.to_global_id not in changed_or_new_gids
        ):
            continue

        # Both endpoints must be present in the new model
        if rel.from_global_id not in all_new_gids or rel.to_global_id not in all_new_gids:
            continue

        try:
            age_client.create_edge(
                from_gid=rel.from_global_id,
                to_gid=rel.to_global_id,
                rel_type=rel.relationship_type,
                rev_id=rev_id,
            )
            created += 1
        except Exception as exc:
            logger.warning(
                "Failed to create edge %s -[%s]-> %s: %s",
                rel.from_global_id,
                rel.relationship_type,
                rel.to_global_id,
                exc,
            )
    return created


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def ingest_ifc(
    ifc_path: str,
    label: str | None = None,
) -> IngestionResult:
    """Ingest an IFC file, creating a new revision with diff-aware SCD2 storage.

    This is the main entry point for the versioned ingestion pipeline.  It
    performs the following steps:

    1. Open the IFC model and extract products + relationships (Phase 1).
    2. Create a ``revisions`` row.
    3. Load current ``content_hash`` values and diff against new products.
    4. Close SCD2 rows for modified/deleted products (``valid_to_rev``).
    5. Insert new SCD2 rows for added/modified products.
    6. Close graph nodes + edges for modified/deleted products.
    7. Create graph nodes for added/modified products.
    8. Create graph edges for relationships involving changed products.

    Steps 2-5 run in a **single relational transaction** for atomicity.
    Graph operations (6-8) are best-effort; failures are logged as warnings
    but do not roll back the relational changes.

    Args:
        ifc_path: Filesystem path to the IFC file.
        label: Optional human-readable label for the revision
               (e.g. ``"v2.1 - structural update"``).

    Returns:
        An :class:`IngestionResult` summarising the ingestion.

    Raises:
        FileNotFoundError: If *ifc_path* does not exist.
        Exception: Relational transaction errors are propagated.
    """
    ifc_filename = Path(ifc_path).name
    logger.info("Starting ingestion of %s", ifc_filename)

    # ---- Phase 1: Extract from IFC ----------------------------------------
    model = ifcopenshell.open(ifc_path)
    records = extract_products_from_model(model)
    relationships = _extract_relationships(model)
    new_by_gid: dict[str, IfcProductRecord] = {r.global_id: r for r in records}
    all_new_gids = set(new_by_gid.keys())

    logger.info(
        "Extracted %d products, %d relationships from %s",
        len(records),
        len(relationships),
        ifc_filename,
    )

    # ---- Phase 2: Diff-aware ingestion (relational -- single transaction) --
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            # Step 2: Create revision
            rev_id = _create_revision(cur, ifc_filename, label)
            logger.info("Created revision %d for %s", rev_id, ifc_filename)

            # Step 3: Load current hashes & diff
            current_hashes = _load_current_hashes(cur)
            added, modified, deleted_gids, unchanged_gids = _diff_products(
                records, current_hashes
            )
            logger.info(
                "Revision %d diff: %d added, %d modified, %d deleted, %d unchanged",
                rev_id,
                len(added),
                len(modified),
                len(deleted_gids),
                len(unchanged_gids),
            )

            # Step 4: Close modified/deleted rows
            close_gids = list(deleted_gids | {r.global_id for r in modified})
            _close_product_rows(cur, close_gids, rev_id)

            # Step 5: Insert added/modified rows
            insert_records = added + modified
            _insert_product_rows(cur, insert_records, rev_id)

        conn.commit()
        logger.info("Relational changes committed for revision %d", rev_id)
    except Exception:
        conn.rollback()
        raise
    finally:
        put_conn(conn)

    # ---- Phase 2 continued: Graph changes (best-effort) -------------------
    modified_gids = {r.global_id for r in modified}
    added_gids = {r.global_id for r in added}
    changed_or_new_gids = added_gids | modified_gids

    # Step 6: Close graph nodes + edges for modified/deleted
    gids_to_close = deleted_gids | modified_gids
    if gids_to_close:
        logger.info(
            "Closing %d graph nodes (+ edges) for revision %d",
            len(gids_to_close),
            rev_id,
        )
        _close_graph_entities(gids_to_close, rev_id)

    # Step 7: Create graph nodes for added/modified
    if insert_records:
        logger.info(
            "Creating %d graph nodes for revision %d",
            len(insert_records),
            rev_id,
        )
        _create_graph_nodes(insert_records, rev_id)

    # Step 8: Create edges for relationships involving changed products
    edges_created = _create_graph_edges(
        relationships, changed_or_new_gids, all_new_gids, rev_id
    )
    logger.info(
        "Created %d graph edges for revision %d",
        edges_created,
        rev_id,
    )

    result = IngestionResult(
        revision_id=rev_id,
        total_products=len(records),
        added=len(added),
        modified=len(modified),
        deleted=len(deleted_gids),
        unchanged=len(unchanged_gids),
        edges_created=edges_created,
    )
    logger.info("Ingestion complete: %s", result)
    return result
