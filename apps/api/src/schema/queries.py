"""Root Query and Mutation resolvers for the BimAtlas GraphQL API.

Streaming helpers for the /stream/ifc-products SSE endpoint live here so
product row → JSON dict conversion stays in one place.

All IFC queries require a ``branchId`` and accept an optional ``revision``
parameter (defaults to latest on that branch).  Project/branch management
is exposed via both queries and mutations.

Resolvers join relational data from :mod:`src.db` (product attributes,
geometry BYTEAs) with graph data from :mod:`src.services.graph.age_client`
(relations, spatial tree).
"""

from __future__ import annotations

import base64
from typing import Any, Optional

import strawberry

from ..db import (
    apply_filter_sets,
    create_branch,
    create_filter_set as db_create_filter_set,
    create_project,
    delete_filter_set as db_delete_filter_set,
    fetch_applied_filter_sets,
    fetch_branch,
    fetch_branches,
    fetch_filter_set,
    fetch_filter_sets_for_branch,
    fetch_product_at_revision,
    fetch_products_at_revision,
    fetch_project,
    fetch_projects,
    fetch_revision_diff,
    fetch_revisions,
    fetch_spatial_container,
    get_latest_revision_id,
    search_filter_sets,
    update_filter_set as db_update_filter_set,
)
from ..services.graph.age_client import build_spatial_tree, get_relations
from .ifc_enums import IfcRelationshipType
from .ifc_types import (
    AppliedFilterSets,
    Branch,
    ChangeType,
    FilterInput,
    FilterSet,
    FilterSetFilter,
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


def row_to_stream_product(row: dict) -> dict[str, Any]:
    """Convert a product row to a JSON-serializable dict (camelCase, base64 mesh) for SSE stream.

    Does not fetch contained_in or relations; use for streaming geometry only.
    """
    mesh = None
    if row.get("vertices") and row.get("faces"):
        mesh = {
            "vertices": base64.b64encode(bytes(row["vertices"])).decode("utf-8"),
            "normals": (
                base64.b64encode(bytes(row["normals"])).decode("utf-8")
                if row.get("normals")
                else None
            ),
            "faces": base64.b64encode(bytes(row["faces"])).decode("utf-8"),
        }
    return {
        "globalId": row["global_id"],
        "ifcClass": row["ifc_class"],
        "name": row.get("name"),
        "description": row.get("description"),
        "objectType": row.get("object_type"),
        "tag": row.get("tag"),
        "mesh": mesh,
    }


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


def _row_to_filter_set(row: dict) -> FilterSet:
    """Convert a db row dict into a :class:`FilterSet` GraphQL type."""
    filters_data = row.get("filters") or []
    if isinstance(filters_data, str):
        import json
        filters_data = json.loads(filters_data)
    return FilterSet(
        id=row["id"],
        branch_id=row["branch_id"],
        name=row["name"],
        logic=row["logic"],
        filters=[
            FilterSetFilter(
                mode=f.get("mode", "class"),
                ifc_class=f.get("ifcClass") or f.get("ifc_class"),
                attribute=f.get("attribute"),
                value=f.get("value"),
            )
            for f in filters_data
        ],
        created_at=_to_iso(row["created_at"]),
        updated_at=_to_iso(row["updated_at"]),
    )


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
        ifc_classes: Optional[list[str]] = None,
        contained_in: Optional[str] = None,
        name: Optional[str] = None,
        object_type: Optional[str] = None,
        tag: Optional[str] = None,
        description: Optional[str] = None,
        global_id: Optional[str] = None,
        revision: Optional[int] = None,
    ) -> list[IfcProduct]:
        """List products visible at a revision on a branch, optionally filtered."""
        rev = _resolve_revision(branch_id, revision)
        rows = fetch_products_at_revision(
            rev,
            branch_id,
            ifc_class=ifc_class,
            ifc_classes=ifc_classes,
            contained_in=contained_in,
            name=name,
            object_type=object_type,
            tag=tag,
            description=description,
            global_id=global_id,
        )
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

    # ---- Filter set queries ------------------------------------------------

    @strawberry.field
    async def filter_sets(self, branch_id: int) -> list[FilterSet]:
        """List all filter sets for a branch."""
        rows = fetch_filter_sets_for_branch(branch_id)
        return [_row_to_filter_set(r) for r in rows]

    @strawberry.field
    async def search_filter_sets(
        self,
        query: str,
        branch_id: Optional[int] = None,
        project_id: Optional[int] = None,
    ) -> list[FilterSet]:
        """Search filter sets by name, optionally scoped to a branch or project."""
        rows = search_filter_sets(query, branch_id=branch_id, project_id=project_id)
        return [_row_to_filter_set(r) for r in rows]

    @strawberry.field
    async def applied_filter_sets(self, branch_id: int) -> AppliedFilterSets:
        """Get the currently active filter sets for a branch."""
        data = fetch_applied_filter_sets(branch_id)
        return AppliedFilterSets(
            filter_sets=[_row_to_filter_set(fs) for fs in data["filter_sets"]],
            combination_logic=data["combination_logic"],
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

    # ---- Filter set mutations -----------------------------------------------

    @strawberry.mutation
    async def create_filter_set(
        self,
        branch_id: int,
        name: str,
        logic: str,
        filters: list[FilterInput],
    ) -> FilterSet:
        """Create a new filter set on a branch."""
        filters_json = [
            {
                "mode": f.mode,
                "ifcClass": f.ifc_class,
                "attribute": f.attribute,
                "value": f.value,
            }
            for f in filters
        ]
        row = db_create_filter_set(branch_id, name, logic, filters_json)
        return _row_to_filter_set(row)

    @strawberry.mutation
    async def update_filter_set(
        self,
        id: int,
        name: Optional[str] = None,
        logic: Optional[str] = None,
        filters: Optional[list[FilterInput]] = None,
    ) -> Optional[FilterSet]:
        """Update an existing filter set."""
        filters_json = (
            [
                {
                    "mode": f.mode,
                    "ifcClass": f.ifc_class,
                    "attribute": f.attribute,
                    "value": f.value,
                }
                for f in filters
            ]
            if filters is not None
            else None
        )
        row = db_update_filter_set(id, name=name, logic=logic, filters_json=filters_json)
        return _row_to_filter_set(row) if row else None

    @strawberry.mutation
    async def delete_filter_set(self, id: int) -> bool:
        """Delete a filter set by id."""
        return db_delete_filter_set(id)

    @strawberry.mutation
    async def apply_filter_sets(
        self,
        branch_id: int,
        filter_set_ids: list[int],
        combination_logic: str,
    ) -> AppliedFilterSets:
        """Set which filter sets are currently active on a branch."""
        apply_filter_sets(branch_id, filter_set_ids, combination_logic)
        data = fetch_applied_filter_sets(branch_id)
        return AppliedFilterSets(
            filter_sets=[_row_to_filter_set(fs) for fs in data["filter_sets"]],
            combination_logic=data["combination_logic"],
        )
