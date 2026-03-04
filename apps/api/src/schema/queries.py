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
import json
import struct
from typing import Any, Optional

import strawberry

from ..db import (
    apply_filter_sets,
    create_branch,
    create_filter_set as db_create_filter_set,
    create_project,
    create_sheet_template as db_create_sheet_template,
    delete_branch as db_delete_branch,
    delete_sheet_template as db_delete_sheet_template,
    delete_filter_set as db_delete_filter_set,
    delete_project as db_delete_project,
    delete_revision as db_delete_revision,
    fetch_applied_filter_sets,
    fetch_branch,
    fetch_branches,
    fetch_filter_set,
    fetch_filter_sets_for_branch,
    fetch_distinct_ifc_classes_at_revision,
    fetch_entity_at_revision,
    fetch_entities_at_revision,
    fetch_project,
    fetch_projects,
    fetch_revision_diff,
    fetch_revisions,
    fetch_revisions_filtered,
    fetch_shape_representations_for_product,
    fetch_shape_reps_for_products,
    fetch_sheet_template,
    fetch_sheet_templates_for_project,
    fetch_sheet_templates_opened,
    fetch_spatial_container,
    update_sheet_template as db_update_sheet_template,
    get_latest_revision_seq,
    search_filter_sets,
    search_sheet_templates,
    update_filter_set as db_update_filter_set,
)
from ..services.graph.age_client import build_spatial_tree, get_element_relations, get_relations
from .ifc_enums import IfcRelationshipType
from . import ifc_schema_loader
from .ifc_types import (
    AppliedFilterSets,
    Branch,
    ChangeType,
    FilterInput,
    FilterSet,
    FilterSetFilter,
    SheetTemplate,
    IfcMeshRepresentation,
    IfcProduct,
    IfcProductClassNode,
    IfcRelatedProduct,
    IfcRelationEdge,
    IfcShapeRepresentation,
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


def _unpack_geometry(
    geometry: Any,
) -> tuple[bytes | None, bytes | None, bytes | None, bytes | None]:
    """Inverse of the `_pack_geometry` helper in `geometry.py`.

    Layout: four big-endian uint64 lengths (vertices, normals, faces, matrix)
    followed by the raw buffers.
    """
    if geometry is None:
        return None, None, None, None
    buf = bytes(geometry)
    if len(buf) < 32:
        return None, None, None, None
    offset = 0
    lengths: list[int] = []
    for _ in range(4):
        (length,) = struct.unpack_from(">Q", buf, offset)
        offset += 8
        lengths.append(int(length))
    out: list[bytes | None] = []
    for length in lengths:
        if length <= 0:
            out.append(None)
        else:
            out.append(buf[offset : offset + length])
            offset += length
    while len(out) < 4:
        out.append(None)
    return out[0], out[1], out[2], out[3]


def _build_stream_mesh_from_shape_rows(shape_rows: list[dict]) -> dict[str, Any] | None:
    """Select a mesh from shape rep rows, preferring the 'Body' representation."""
    candidates: list[tuple[str | None, bytes | None, bytes | None, bytes | None]] = []
    for row in shape_rows:
        attrs = row.get("attributes") or {}
        if isinstance(attrs, str):
            attrs = json.loads(attrs)
        rep_id = attrs.get("RepresentationIdentifier")
        vertices, normals, faces, _matrix = _unpack_geometry(row.get("geometry"))
        if vertices is None or faces is None:
            continue
        candidates.append((rep_id, vertices, normals, faces))

    if not candidates:
        return None

    # Prefer Body; otherwise take the first available mesh.
    chosen = None
    for rep_id, vertices, normals, faces in candidates:
        if (rep_id or "").lower() == "body":
            chosen = (vertices, normals, faces)
            break
    if chosen is None:
        _, vertices, normals, faces = candidates[0]
        chosen = (vertices, normals, faces)

    vertices, normals, faces = chosen
    return {
        "vertices": base64.b64encode(vertices).decode("utf-8"),
        "normals": base64.b64encode(normals).decode("utf-8") if normals is not None else None,
        "faces": base64.b64encode(faces).decode("utf-8"),
    }


def row_to_stream_product(
    row: dict,
    rev: int,
    branch_id: str,
    shape_rows: list[dict] | None = None,
) -> dict[str, Any]:
    """Convert an entity row + optional shape reps into a streamable product dict."""
    attrs = row.get("attributes") or {}
    if isinstance(attrs, str):
        attrs = json.loads(attrs)

    mesh = None
    if shape_rows:
        mesh = _build_stream_mesh_from_shape_rows(shape_rows)

    # Fallback for legacy rows where geometry still lives on the product.
    if mesh is None:
        vertices, normals, faces, _matrix = _unpack_geometry(row.get("geometry"))
        if vertices is not None and faces is not None:
            mesh = {
                "vertices": base64.b64encode(vertices).decode("utf-8"),
                "normals": base64.b64encode(normals).decode("utf-8")
                if normals is not None
                else None,
                "faces": base64.b64encode(faces).decode("utf-8"),
            }

    return {
        "globalId": row["ifc_global_id"],
        "ifcClass": row["ifc_class"],
        "name": attrs.get("Name"),
        "description": attrs.get("Description"),
        "objectType": attrs.get("ObjectType"),
        "tag": attrs.get("Tag"),
        "attributes": attrs,
        "mesh": mesh,
    }


def _resolve_revision(branch_id: str, revision: int | None) -> int:
    """Resolve an optional revision parameter to a concrete revision_seq for a branch."""
    if revision is not None:
        return revision
    latest = get_latest_revision_seq(branch_id)
    if latest is None:
        raise ValueError("No revisions exist on this branch -- upload an IFC file first")
    return latest


def _row_to_product(row: dict, rev: int, branch_id: str) -> IfcProduct:
    """Convert an ``ifc_entity`` row dict into an :class:`IfcProduct` GraphQL type."""
    attrs = row.get("attributes") or {}
    if isinstance(attrs, str):
        attrs = json.loads(attrs)

    mesh: IfcMeshRepresentation | None = None
    representations: list[IfcShapeRepresentation] = []

    # --- Shape representations + mesh (prefer Body) -------------------------
    shape_rows = fetch_shape_representations_for_product(row["ifc_global_id"], rev, branch_id)
    if shape_rows:
        for srow in shape_rows:
            s_attrs = srow.get("attributes") or {}
            if isinstance(s_attrs, str):
                s_attrs = json.loads(s_attrs)
            rep_id = s_attrs.get("RepresentationIdentifier")
            rep_type = s_attrs.get("RepresentationType")
            s_vertices, s_normals, s_faces, _s_matrix = _unpack_geometry(srow.get("geometry"))
            shape_mesh: IfcMeshRepresentation | None = None
            if s_vertices is not None and s_faces is not None:
                shape_mesh = IfcMeshRepresentation(
                    vertices=s_vertices,
                    normals=s_normals,
                    faces=s_faces,
                )
            representations.append(
                IfcShapeRepresentation(
                    global_id=srow["ifc_global_id"],
                    representation_identifier=rep_id,
                    representation_type=rep_type,
                    mesh=shape_mesh,
                )
            )

        # Choose a Body representation with mesh as the primary product mesh.
        for rep in representations:
            if rep.mesh is None:
                continue
            ident = (rep.representation_identifier or "").lower()
            if ident == "body":
                mesh = rep.mesh
                break
        if mesh is None:
            for rep in representations:
                if rep.mesh is not None:
                    mesh = rep.mesh
                    break

    # Fallback for legacy rows where geometry still lives on the product.
    if mesh is None:
        vertices, normals, faces, _matrix = _unpack_geometry(row.get("geometry"))
        if vertices is not None and faces is not None:
            mesh = IfcMeshRepresentation(
                vertices=vertices,
                normals=normals,
                faces=faces,
            )

    # --- Spatial container reference ----------------------------------------
    contained_in_ref: IfcSpatialContainerRef | None = None
    contained_in_gid = attrs.get("ContainedIn")
    if contained_in_gid:
        container = fetch_spatial_container(contained_in_gid, rev, branch_id)
        if container:
            c_attrs = container.get("attributes") or {}
            if isinstance(c_attrs, str):
                c_attrs = json.loads(c_attrs)
            contained_in_ref = IfcSpatialContainerRef(
                global_id=container["ifc_global_id"],
                ifc_class=container["ifc_class"],
                name=c_attrs.get("Name"),
            )

    # --- Relations from the graph -------------------------------------------
    try:
        relation_dicts = get_relations(row["ifc_global_id"], rev, branch_id)
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
        global_id=row["ifc_global_id"],
        ifc_class=row["ifc_class"],
        name=attrs.get("Name"),
        description=attrs.get("Description"),
        object_type=attrs.get("ObjectType"),
        tag=attrs.get("Tag"),
        contained_in=contained_in_ref,
        mesh=mesh,
        relations=relations,
        predefined_type=attrs.get("PredefinedType"),
        representations=representations,
        property_sets=attrs.get("PropertySets"),
        attributes=attrs,
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
        filters_data = json.loads(filters_data)
    return FilterSet(
        id=row["filter_set_id"],
        branch_id=row["branch_id"],
        name=row["name"],
        logic=row["logic"],
        filters=[
            FilterSetFilter(
                mode=f.get("mode", "class"),
                ifc_class=f.get("ifcClass") or f.get("ifc_class"),
                attribute=f.get("attribute"),
                value=f.get("value"),
                relation=f.get("relation"),
            )
            for f in filters_data
        ],
        created_at=_to_iso(row["created_at"]),
        updated_at=_to_iso(row["updated_at"]),
    )


def _row_to_sheet_template(row: dict) -> SheetTemplate:
    """Convert a db row dict into a :class:`SheetTemplate` GraphQL type."""
    sheet = row.get("sheet") or {}
    if isinstance(sheet, str):
        sheet = json.loads(sheet) if sheet else {}
    return SheetTemplate(
        id=row["sheet_template_id"],
        project_id=row["project_id"],
        name=row["name"],
        sheet=sheet,
        open=row.get("open", False),
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
            branches = fetch_branches(r["project_id"])
            result.append(
                Project(
                    id=r["project_id"],
                    name=r["name"],
                    description=r.get("description"),
                    created_at=_to_iso(r["created_at"]),
                    branches=[
                        Branch(
                            id=b["branch_id"],
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
    async def project(self, project_id: str) -> Optional[Project]:
        """Fetch a single project by id."""
        r = fetch_project(project_id)
        if r is None:
            return None
        branches = fetch_branches(r["project_id"])
        return Project(
            id=r["project_id"],
            name=r["name"],
            description=r.get("description"),
            created_at=_to_iso(r["created_at"]),
            branches=[
                Branch(
                    id=b["branch_id"],
                    project_id=b["project_id"],
                    name=b["name"],
                    created_at=_to_iso(b["created_at"]),
                )
                for b in branches
            ],
        )

    @strawberry.field
    async def branches(self, project_id: str) -> list[Branch]:
        """List all branches for a project."""
        rows = fetch_branches(project_id)
        return [
            Branch(
                id=b["branch_id"],
                project_id=b["project_id"],
                name=b["name"],
                created_at=_to_iso(b["created_at"]),
            )
            for b in rows
        ]

    # ---- IFC queries (branch-scoped) ---------------------------------------

    @strawberry.field
    async def ifc_product(
        self, branch_id: str, global_id: str, revision: Optional[int] = None
    ) -> Optional[IfcProduct]:
        """Fetch a single product at a specific revision on a branch (default: latest)."""
        rev = _resolve_revision(branch_id, revision)
        row = fetch_entity_at_revision(global_id, rev, branch_id)
        if row is None:
            return None
        return _row_to_product(row, rev, branch_id)

    @strawberry.field
    async def ifc_products(
        self,
        branch_id: str,
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
        rows = fetch_entities_at_revision(
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
    async def ifc_product_tree(
        self,
        branch_id: str,
        revision: Optional[int] = None,
    ) -> Optional[IfcProductClassNode]:
        """IFC product class hierarchy rooted at IfcProduct, pruned to classes present in the DB."""
        rev = _resolve_revision(branch_id, revision)
        present_classes = set(fetch_distinct_ifc_classes_at_revision(rev, branch_id))
        if not present_classes:
            return None

        root_name = "IfcProduct"
        if ifc_schema_loader.get_entity(root_name) is None:
            return None

        def build_node(name: str) -> Optional[IfcProductClassNode]:
            children_nodes: list[IfcProductClassNode] = []
            for child in ifc_schema_loader.get_children(name):
                subtree = build_node(child)
                if subtree is not None:
                    children_nodes.append(subtree)

            if name not in present_classes and not children_nodes:
                return None

            return IfcProductClassNode(ifc_class=name, children=children_nodes)

        root = build_node(root_name)
        return root

    @strawberry.field
    async def spatial_tree(self, branch_id: str, revision: Optional[int] = None) -> list[IfcSpatialNode]:
        """Spatial decomposition tree at a specific revision on a branch."""
        rev = _resolve_revision(branch_id, revision)
        try:
            tree_data = build_spatial_tree(rev, branch_id)
        except Exception:
            return []
        return [_dict_to_spatial_node(d) for d in tree_data]

    @strawberry.field
    async def element_relations(
        self,
        branch_id: str,
        revision: Optional[int] = None,
        relation_types: Optional[list[IfcRelationshipType]] = None,
    ) -> list[IfcRelationEdge]:
        """Non-spatial element relations (voIds, fills, connects, type-defines, shape reps)."""
        rev = _resolve_revision(branch_id, revision)
        if relation_types:
            rel_labels = [rt.value for rt in relation_types]
        else:
            rel_labels = [
                IfcRelationshipType.REL_VOIDS_ELEMENT.value,
                IfcRelationshipType.REL_FILLS_ELEMENT.value,
                IfcRelationshipType.REL_CONNECTS_ELEMENTS.value,
                IfcRelationshipType.REL_DEFINES_BY_TYPE.value,
                IfcRelationshipType.HAS_SHAPE_REPRESENTATION.value,
            ]

        raw_edges = get_element_relations(rel_labels, rev, branch_id)
        edges: list[IfcRelationEdge] = []
        for e in raw_edges:
            try:
                rel_type = IfcRelationshipType(e["relationship"])
            except ValueError:
                # Skip edges we don't have enum coverage for
                continue
            edges.append(
                IfcRelationEdge(
                    source_id=e["source_id"],
                    source_ifc_class=e["source_class"],
                    source_name=e.get("source_name"),
                    target_id=e["target_id"],
                    target_ifc_class=e["target_class"],
                    target_name=e.get("target_name"),
                    relationship=rel_type,
                )
            )
        return edges

    @strawberry.field
    async def revisions(
        self,
        branch_id: str,
        search: Optional[str] = None,
        author_search: Optional[str] = None,
        ifc_filename_search: Optional[str] = None,
        commit_message_search: Optional[str] = None,
        created_after: Optional[str] = None,
        created_before: Optional[str] = None,
    ) -> list[Revision]:
        """List revisions on a branch, optionally filtered by search terms (all parameterized)."""
        if any(
            x is not None and (x.strip() if isinstance(x, str) else True)
            for x in (
                search,
                author_search,
                ifc_filename_search,
                commit_message_search,
                created_after,
                created_before,
            )
        ):
            rows = fetch_revisions_filtered(
                branch_id,
                search=search or None,
                author_search=author_search or None,
                ifc_filename_search=ifc_filename_search or None,
                commit_message_search=commit_message_search or None,
                created_after=created_after or None,
                created_before=created_before or None,
            )
        else:
            rows = fetch_revisions(branch_id)
        return [
            Revision(
                id=r["revision_id"],
                branch_id=r["branch_id"],
                revision_seq=r["revision_seq"],
                label=r.get("commit_message"),
                ifc_filename=r["ifc_filename"],
                author_id=r.get("author_id"),
                created_at=_to_iso(r["created_at"]),
            )
            for r in rows
        ]

    @strawberry.field
    async def revision_diff(self, branch_id: str, from_rev: int, to_rev: int) -> RevisionDiff:
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
    async def filter_sets(self, branch_id: str) -> list[FilterSet]:
        """List all filter sets for a branch."""
        rows = fetch_filter_sets_for_branch(branch_id)
        return [_row_to_filter_set(r) for r in rows]

    @strawberry.field
    async def search_filter_sets(
        self,
        query: str,
        branch_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> list[FilterSet]:
        """Search filter sets by name, optionally scoped to a branch or project."""
        rows = search_filter_sets(query, branch_id=branch_id, project_id=project_id)
        return [_row_to_filter_set(r) for r in rows]

    @strawberry.field
    async def applied_filter_sets(self, branch_id: str) -> AppliedFilterSets:
        """Get the currently active filter sets for a branch."""
        data = fetch_applied_filter_sets(branch_id)
        return AppliedFilterSets(
            filter_sets=[_row_to_filter_set(fs) for fs in data["filter_sets"]],
            combination_logic=data["combination_logic"],
        )

    # ---- Sheet template queries --------------------------------------------

    @strawberry.field
    async def sheet_templates(self, project_id: str) -> list[SheetTemplate]:
        """List all sheet templates for a project."""
        rows = fetch_sheet_templates_for_project(project_id)
        return [_row_to_sheet_template(r) for r in rows]

    @strawberry.field
    async def opened_sheet_templates(self, project_id: str) -> list[SheetTemplate]:
        """List sheet templates with open=True for a project (for initial load)."""
        rows = fetch_sheet_templates_opened(project_id)
        return [_row_to_sheet_template(r) for r in rows]

    @strawberry.field
    async def search_sheet_templates(
        self,
        query: str,
        project_id: str,
    ) -> list[SheetTemplate]:
        """Search sheet templates by name within a project."""
        rows = search_sheet_templates(query, project_id)
        return [_row_to_sheet_template(r) for r in rows]

    @strawberry.field
    async def sheet_template(self, id: str) -> Optional[SheetTemplate]:
        """Fetch a single sheet template by id."""
        row = fetch_sheet_template(id)
        return _row_to_sheet_template(row) if row else None


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def create_project(self, name: str, description: Optional[str] = None) -> Project:
        """Create a new project with a default 'main' branch."""
        proj = create_project(name, description)
        branches = fetch_branches(proj["project_id"])
        return Project(
            id=proj["project_id"],
            name=proj["name"],
            description=proj.get("description"),
            created_at=_to_iso(proj["created_at"]),
            branches=[
                Branch(
                    id=b["branch_id"],
                    project_id=b["project_id"],
                    name=b["name"],
                    created_at=_to_iso(b["created_at"]),
                )
                for b in branches
            ],
        )

    @strawberry.mutation
    async def create_branch(self, project_id: str, name: str) -> Branch:
        """Create a new branch within a project."""
        b = create_branch(project_id, name)
        return Branch(
            id=b["branch_id"],
            project_id=b["project_id"],
            name=b["name"],
            created_at=_to_iso(b["created_at"]),
        )

    @strawberry.mutation
    async def delete_project(self, id: str) -> bool:
        """Delete a project and all its branches, revisions, and model data."""
        return db_delete_project(id)

    @strawberry.mutation
    async def delete_branch(self, id: str) -> bool:
        """Delete a branch and all its revisions and model data."""
        return db_delete_branch(id)

    @strawberry.mutation
    async def delete_revision(self, id: str) -> bool:
        """Delete a revision and clean up referencing product rows."""
        return db_delete_revision(id)

    # ---- Filter set mutations -----------------------------------------------

    @strawberry.mutation
    async def create_filter_set(
        self,
        branch_id: str,
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
                "relation": f.relation,
            }
            for f in filters
        ]
        row = db_create_filter_set(branch_id, name, logic, filters_json)
        return _row_to_filter_set(row)

    @strawberry.mutation
    async def update_filter_set(
        self,
        id: str,
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
                    "relation": f.relation,
                }
                for f in filters
            ]
            if filters is not None
            else None
        )
        row = db_update_filter_set(id, name=name, logic=logic, filters_json=filters_json)
        return _row_to_filter_set(row) if row else None

    @strawberry.mutation
    async def delete_filter_set(self, id: str) -> bool:
        """Delete a filter set by id."""
        return db_delete_filter_set(id)

    @strawberry.mutation
    async def apply_filter_sets(
        self,
        branch_id: str,
        filter_set_ids: list[str],
        combination_logic: str,
    ) -> AppliedFilterSets:
        """Set which filter sets are currently active on a branch."""
        apply_filter_sets(branch_id, filter_set_ids, combination_logic)
        data = fetch_applied_filter_sets(branch_id)
        return AppliedFilterSets(
            filter_sets=[_row_to_filter_set(fs) for fs in data["filter_sets"]],
            combination_logic=data["combination_logic"],
        )

    # ---- Sheet template mutations -----------------------------------------

    @strawberry.mutation
    async def create_sheet_template(
        self,
        project_id: str,
        name: str,
        sheet: strawberry.scalars.JSON,
        open: bool = False,
    ) -> SheetTemplate:
        """Create a new sheet template for a project. Name is required."""
        sheet_dict = sheet if isinstance(sheet, dict) else {}
        row = db_create_sheet_template(project_id, name, sheet_dict, open=open)
        return _row_to_sheet_template(row)

    @strawberry.mutation
    async def update_sheet_template(
        self,
        id: str,
        open: Optional[bool] = None,
        name: Optional[str] = None,
        sheet: Optional[strawberry.scalars.JSON] = None,
    ) -> Optional[SheetTemplate]:
        """Update a sheet template (open, name, or sheet content)."""
        sheet_dict = sheet if isinstance(sheet, dict) else None
        row = db_update_sheet_template(id, open=open, name=name, sheet=sheet_dict)
        return _row_to_sheet_template(row) if row else None

    @strawberry.mutation
    async def delete_sheet_template(self, id: str) -> bool:
        """Delete a sheet template by id."""
        return db_delete_sheet_template(id)
