"""IFC 4.3-aligned Strawberry types.

Type hierarchy mirrors the IFC 4.3 entity inheritance chain:
  IfcRoot -> IfcObjectDefinition -> IfcProduct
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

import strawberry

from .ifc_enums import IfcRelationshipType
from .scalars import Base64Bytes


@strawberry.interface
class IfcRoot:
    """IFC 4.3 sec 5.1 -- All rooted entities carry a GlobalId, Name, Description."""

    global_id: str
    name: Optional[str] = None
    description: Optional[str] = None


@strawberry.interface
class IfcObjectDefinition(IfcRoot):
    """IFC 4.3 sec 5.1 -- Generalisation of any semantically treated thing."""

    pass


@strawberry.type
class IfcMeshRepresentation:
    """Triangulated mesh extracted from IfcProduct.Representation via IfcOpenShell."""

    vertices: Base64Bytes  # Float32Array (x,y,z triples)
    normals: Optional[Base64Bytes] = None  # Float32Array (nx,ny,nz triples) -- may be absent
    faces: Base64Bytes  # Uint32Array  (triangle index triples)


@strawberry.type
class IfcRelatedProduct:
    """A neighboring product reached via an IFC objectified relationship edge."""

    global_id: str
    ifc_class: str
    name: Optional[str] = None
    relationship: IfcRelationshipType


@strawberry.type
class IfcSpatialContainerRef:
    """Reference to the single IfcSpatialStructureElement that contains this product.

    Per IFC 4.3 sec 4.1.5.13, a physical element shall only be contained
    within a single spatial structure (IfcBuildingStorey being the default).
    Resolved from IfcRelContainedInSpatialStructure.
    """

    global_id: str
    ifc_class: str
    name: Optional[str] = None


@strawberry.type
class IfcProduct(IfcObjectDefinition):
    """IFC 4.3 sec 5.1 -- Any object with spatial context.

    This is the unified query type returned by BimAtlas.
    Covers both IfcElement subtypes and IfcSpatialStructureElement subtypes.
    """

    ifc_class: str
    object_type: Optional[str] = None
    tag: Optional[str] = None
    contained_in: Optional[IfcSpatialContainerRef] = None
    mesh: Optional[IfcMeshRepresentation] = None
    neighbors: list[IfcRelatedProduct] = strawberry.field(default_factory=list)


@strawberry.type
class IfcSpatialNode:
    """A node in the spatial decomposition tree (IfcRelAggregates).

    Recursive: Project -> Site -> Building -> Storey -> Space.
    """

    global_id: str
    ifc_class: str
    name: Optional[str] = None
    children: list[IfcSpatialNode] = strawberry.field(default_factory=list)
    contained_elements: list[IfcRelatedProduct] = strawberry.field(default_factory=list)


# -- Versioning types --


@strawberry.enum
class ChangeType(Enum):
    ADDED = "ADDED"
    MODIFIED = "MODIFIED"
    DELETED = "DELETED"


@strawberry.type
class Revision:
    id: int
    label: Optional[str]
    ifc_filename: str
    created_at: str  # ISO 8601


@strawberry.type
class RevisionDiffEntry:
    global_id: str
    ifc_class: str
    name: Optional[str]
    change_type: ChangeType


@strawberry.type
class RevisionDiff:
    from_revision: int
    to_revision: int
    added: list[RevisionDiffEntry]
    modified: list[RevisionDiffEntry]
    deleted: list[RevisionDiffEntry]
