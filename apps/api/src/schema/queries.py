"""Root Query and Mutation resolvers for the BimAtlas GraphQL API.

All IFC queries require a ``branchId`` and accept an optional ``revision``
parameter (defaults to latest on that branch).  Project/branch management
is exposed via both queries and mutations.

Resolvers join relational data from :mod:`src.db` (product attributes,
geometry BYTEAs) with graph data from :mod:`src.services.graph.age_client`
(relations, spatial tree).
"""

from __future__ import annotations

from typing import Optional

import strawberry

from ..db import (
    create_branch,
    create_project,
    fetch_branch,
    fetch_branches,
    fetch_product_at_revision,
    fetch_products_at_revision,
    fetch_project,
    fetch_projects,
    fetch_revision_diff,
    fetch_revisions,
    fetch_spatial_container,
    get_latest_revision_id,
)
from ..services.graph.age_client import build_spatial_tree, get_relations
from .ifc_enums import IfcRelationshipType
from .ifc_types import (
    Branch,
    ChangeType,
    IfcMeshRepresentation,
    IfcProduct,
    IfcRelatedProduct,
    IfcSpatialContainerRef,
    IfcSpatialNode,
    Project,
    Revision,
    RevisionDiff,
    RevisionDiffEntry,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_revision(branch_id: int, revision: int | None) -> int:
    """Resolve an optional revision parameter to a concrete id for a branch."""
    if revision is not None:
        return revision
    latest = get_latest_revision_id(branch_id)
    if latest is None:
        raise ValueError("No revisions exist on this branch -- upload an IFC file first")
    return latest


def _row_to_product(row: dict, rev: int, branch_id: int) -> IfcProduct:
    """Convert a relational row dict into an :class:`IfcProduct` GraphQL type."""
    # --- Mesh (only if geometry data exists) --------------------------------
    mesh: IfcMeshRepresentation | None = None
    if row.get("vertices") and row.get("faces"):
        mesh = IfcMeshRepresentation(
            vertices=bytes(row["vertices"]),
            normals=bytes(row["normals"]) if row.get("normals") else None,
            faces=bytes(row["faces"]),
        )

    # --- Spatial container reference ----------------------------------------
    contained_in_ref: IfcSpatialContainerRef | None = None
    if row.get("contained_in"):
        container = fetch_spatial_container(row["contained_in"], rev, branch_id)
        if container:
            contained_in_ref = IfcSpatialContainerRef(
                global_id=container["global_id"],
                ifc_class=container["ifc_class"],
                name=container.get("name"),
            )

    # --- Relations from the graph -------------------------------------------
    try:
        relation_dicts = get_relations(row["global_id"], rev, branch_id)
    except Exception:
        # Graph may not be populated yet; degrade gracefully
        relation_dicts = []

    relations: list[IfcRelatedProduct] = []
    for rd in relation_dicts:
        try:
            rel_type = IfcRelationshipType(rd["relationship"])
        except (ValueError, KeyError):
            continue  # Skip unknown relationship types
        relations.append(
            IfcRelatedProduct(
                global_id=rd["global_id"],
                ifc_class=rd["ifc_class"],
                name=rd.get("name"),
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
        relations=relations,
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


def _to_iso(dt) -> str:
    """Convert a datetime to ISO 8601 string."""
    return dt.isoformat() if hasattr(dt, "isoformat") else str(dt)


# ---------------------------------------------------------------------------
# Root Query
# ---------------------------------------------------------------------------


@strawberry.type
class Query:
    # ---- Project / Branch queries ------------------------------------------

    @strawberry.field
    async def projects(self) -> list[Project]:
        """List all projects with their branches."""
        rows = fetch_projects()
        result = []
        for r in rows:
            branches = fetch_branches(r["id"])
            result.append(
                Project(
                    id=r["id"],
                    name=r["name"],
                    description=r.get("description"),
                    created_at=_to_iso(r["created_at"]),
                    branches=[
                        Branch(
                            id=b["id"],
                            project_id=b["project_id"],
                            name=b["name"],
                            created_at=_to_iso(b["created_at"]),
                        )
                        for b in branches
                    ],
                )
            )
        return result

    @strawberry.field
    async def project(self, project_id: int) -> Optional[Project]:
        """Fetch a single project by id."""
        r = fetch_project(project_id)
        if r is None:
            return None
        branches = fetch_branches(r["id"])
        return Project(
            id=r["id"],
            name=r["name"],
            description=r.get("description"),
            created_at=_to_iso(r["created_at"]),
            branches=[
                Branch(
                    id=b["id"],
                    project_id=b["project_id"],
                    name=b["name"],
                    created_at=_to_iso(b["created_at"]),
                )
                for b in branches
            ],
        )

    @strawberry.field
    async def branches(self, project_id: int) -> list[Branch]:
        """List all branches for a project."""
        rows = fetch_branches(project_id)
        return [
            Branch(
                id=b["id"],
                project_id=b["project_id"],
                name=b["name"],
                created_at=_to_iso(b["created_at"]),
            )
            for b in rows
        ]

    # ---- IFC queries (branch-scoped) ---------------------------------------

    @strawberry.field
    async def ifc_product(
        self, branch_id: int, global_id: str, revision: Optional[int] = None
    ) -> Optional[IfcProduct]:
        """Fetch a single product at a specific revision on a branch (default: latest)."""
        rev = _resolve_revision(branch_id, revision)
        row = fetch_product_at_revision(global_id, rev, branch_id)
        if row is None:
            return None
        return _row_to_product(row, rev, branch_id)

    @strawberry.field
    async def ifc_products(
        self,
        branch_id: int,
        ifc_class: Optional[str] = None,
        contained_in: Optional[str] = None,
        revision: Optional[int] = None,
    ) -> list[IfcProduct]:
        """List products visible at a revision on a branch, optionally filtered."""
        rev = _resolve_revision(branch_id, revision)
        rows = fetch_products_at_revision(rev, branch_id, ifc_class=ifc_class, contained_in=contained_in)
        return [_row_to_product(r, rev, branch_id) for r in rows]

    @strawberry.field
    async def spatial_tree(self, branch_id: int, revision: Optional[int] = None) -> list[IfcSpatialNode]:
        """Spatial decomposition tree at a specific revision on a branch."""
        rev = _resolve_revision(branch_id, revision)
        try:
            tree_data = build_spatial_tree(rev, branch_id)
        except Exception:
            return []
        return [_dict_to_spatial_node(d) for d in tree_data]

    @strawberry.field
    async def revisions(self, branch_id: int) -> list[Revision]:
        """List all revisions on a branch."""
        rows = fetch_revisions(branch_id)
        return [
            Revision(
                id=r["id"],
                branch_id=r["branch_id"],
                label=r.get("label"),
                ifc_filename=r["ifc_filename"],
                created_at=_to_iso(r["created_at"]),
            )
            for r in rows
        ]

    @strawberry.field
    async def revision_diff(self, branch_id: int, from_rev: int, to_rev: int) -> RevisionDiff:
        """Compute the diff between two revisions on the same branch."""
        diff = fetch_revision_diff(from_rev, to_rev, branch_id)
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


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def create_project(self, name: str, description: Optional[str] = None) -> Project:
        """Create a new project with a default 'main' branch."""
        proj = create_project(name, description)
        branches = fetch_branches(proj["id"])
        return Project(
            id=proj["id"],
            name=proj["name"],
            description=proj.get("description"),
            created_at=_to_iso(proj["created_at"]),
            branches=[
                Branch(
                    id=b["id"],
                    project_id=b["project_id"],
                    name=b["name"],
                    created_at=_to_iso(b["created_at"]),
                )
                for b in branches
            ],
        )

    @strawberry.mutation
    async def create_branch(self, project_id: int, name: str) -> Branch:
        """Create a new branch within a project."""
        b = create_branch(project_id, name)
        return Branch(
            id=b["id"],
            project_id=b["project_id"],
            name=b["name"],
            created_at=_to_iso(b["created_at"]),
        )
