"""Root Query resolver for the BimAtlas GraphQL API.

All queries accept an optional ``revision`` parameter (defaults to latest).
Resolvers join relational data from :mod:`src.db` (product attributes,
geometry BYTEAs) with graph data from :mod:`src.services.graph.age_client`
(neighbors, spatial tree).
"""

from __future__ import annotations

from typing import Optional

import strawberry

from ..db import (
    fetch_product_at_revision,
    fetch_products_at_revision,
    fetch_revision_diff,
    fetch_revisions,
    fetch_spatial_container,
    get_latest_revision_id,
)
from ..services.graph.age_client import build_spatial_tree, get_neighbors
from .ifc_enums import IfcRelationshipType
from .ifc_types import (
    ChangeType,
    IfcMeshRepresentation,
    IfcProduct,
    IfcRelatedProduct,
    IfcSpatialContainerRef,
    IfcSpatialNode,
    Revision,
    RevisionDiff,
    RevisionDiffEntry,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_revision(revision: int | None) -> int:
    """Resolve an optional revision parameter to a concrete id."""
    if revision is not None:
        return revision
    latest = get_latest_revision_id()
    if latest is None:
        raise ValueError("No revisions exist yet -- upload an IFC file first")
    return latest


def _row_to_product(row: dict, rev: int) -> IfcProduct:
    """Convert a relational row dict into an :class:`IfcProduct` GraphQL type.

    Enriches the flat row with:
    - ``mesh`` -- decoded from BYTEA columns (``None`` for spatial elements)
    - ``contained_in`` -- resolved to :class:`IfcSpatialContainerRef`
    - ``neighbors`` -- fetched from the AGE graph
    """
    # --- Mesh (only if geometry data exists) --------------------------------
    mesh: IfcMeshRepresentation | None = None
    if row.get("vertices") and row.get("normals") and row.get("faces"):
        mesh = IfcMeshRepresentation(
            vertices=bytes(row["vertices"]),
            normals=bytes(row["normals"]),
            faces=bytes(row["faces"]),
        )

    # --- Spatial container reference ----------------------------------------
    contained_in_ref: IfcSpatialContainerRef | None = None
    if row.get("contained_in"):
        container = fetch_spatial_container(row["contained_in"], rev)
        if container:
            contained_in_ref = IfcSpatialContainerRef(
                global_id=container["global_id"],
                ifc_class=container["ifc_class"],
                name=container.get("name"),
            )

    # --- Neighbors from the graph -------------------------------------------
    try:
        neighbor_dicts = get_neighbors(row["global_id"], rev)
    except Exception:
        # Graph may not be populated yet; degrade gracefully
        neighbor_dicts = []

    neighbors: list[IfcRelatedProduct] = []
    for nd in neighbor_dicts:
        try:
            rel_type = IfcRelationshipType(nd["relationship"])
        except (ValueError, KeyError):
            continue  # Skip unknown relationship types
        neighbors.append(
            IfcRelatedProduct(
                global_id=nd["global_id"],
                ifc_class=nd["ifc_class"],
                name=nd.get("name"),
                relationship=rel_type,
            )
        )

    return IfcProduct(
        global_id=row["global_id"],
        ifc_class=row["ifc_class"],
        name=row.get("name"),
        description=row.get("description"),
        object_type=row.get("object_type"),
        tag=row.get("tag"),
        contained_in=contained_in_ref,
        mesh=mesh,
        neighbors=neighbors,
    )


def _dict_to_spatial_node(d: dict) -> IfcSpatialNode:
    """Recursively convert a spatial tree dict into an :class:`IfcSpatialNode`."""
    return IfcSpatialNode(
        global_id=d["global_id"],
        ifc_class=d["ifc_class"],
        name=d.get("name"),
        children=[_dict_to_spatial_node(c) for c in d.get("children", [])],
        contained_elements=[
            IfcRelatedProduct(
                global_id=e["global_id"],
                ifc_class=e["ifc_class"],
                name=e.get("name"),
                relationship=IfcRelationshipType.REL_CONTAINED_IN_SPATIAL,
            )
            for e in d.get("contained_elements", [])
        ],
    )


# ---------------------------------------------------------------------------
# Root Query
# ---------------------------------------------------------------------------


@strawberry.type
class Query:
    @strawberry.field
    async def ifc_product(
        self, global_id: str, revision: Optional[int] = None
    ) -> Optional[IfcProduct]:
        """Fetch a single product at a specific revision (default: latest)."""
        rev = _resolve_revision(revision)
        row = fetch_product_at_revision(global_id, rev)
        if row is None:
            return None
        return _row_to_product(row, rev)

    @strawberry.field
    async def ifc_products(
        self,
        ifc_class: Optional[str] = None,
        contained_in: Optional[str] = None,
        revision: Optional[int] = None,
    ) -> list[IfcProduct]:
        """List products visible at a revision, optionally filtered by class or container."""
        rev = _resolve_revision(revision)
        rows = fetch_products_at_revision(rev, ifc_class=ifc_class, contained_in=contained_in)
        return [_row_to_product(r, rev) for r in rows]

    @strawberry.field
    async def spatial_tree(self, revision: Optional[int] = None) -> list[IfcSpatialNode]:
        """Spatial decomposition tree at a specific revision."""
        rev = _resolve_revision(revision)
        try:
            tree_data = build_spatial_tree(rev)
        except Exception:
            # Graph may not be populated; return empty tree
            return []
        return [_dict_to_spatial_node(d) for d in tree_data]

    @strawberry.field
    async def revisions(self) -> list[Revision]:
        """List all ingested revisions."""
        rows = fetch_revisions()
        return [
            Revision(
                id=r["id"],
                label=r.get("label"),
                ifc_filename=r["ifc_filename"],
                created_at=(
                    r["created_at"].isoformat()
                    if hasattr(r["created_at"], "isoformat")
                    else str(r["created_at"])
                ),
            )
            for r in rows
        ]

    @strawberry.field
    async def revision_diff(self, from_rev: int, to_rev: int) -> RevisionDiff:
        """Compute the diff between two revisions: added, modified, deleted products."""
        diff = fetch_revision_diff(from_rev, to_rev)
        return RevisionDiff(
            from_revision=from_rev,
            to_revision=to_rev,
            added=[
                RevisionDiffEntry(
                    global_id=r["global_id"],
                    ifc_class=r["ifc_class"],
                    name=r.get("name"),
                    change_type=ChangeType.ADDED,
                )
                for r in diff["added"]
            ],
            modified=[
                RevisionDiffEntry(
                    global_id=r["global_id"],
                    ifc_class=r["ifc_class"],
                    name=r.get("name"),
                    change_type=ChangeType.MODIFIED,
                )
                for r in diff["modified"]
            ],
            deleted=[
                RevisionDiffEntry(
                    global_id=r["global_id"],
                    ifc_class=r["ifc_class"],
                    name=r.get("name"),
                    change_type=ChangeType.DELETED,
                )
                for r in diff["deleted"]
            ],
        )
