"""IFC 4.3-aligned Strawberry types.

Type hierarchy mirrors the IFC 4.3 entity inheritance chain:
  IfcRoot -> IfcObjectDefinition -> IfcProduct

Also includes Project and Branch types for multi-project, multi-branch
organisation.
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
    """A related product reached via an IFC objectified relationship edge."""

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
    relations: list[IfcRelatedProduct] = strawberry.field(default_factory=list)


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
    branch_id: int
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


# -- Project / Branch types --


@strawberry.type
class Branch:
    """A branch within a project. Each branch has an independent revision history."""

    id: int
    project_id: int
    name: str
    created_at: str  # ISO 8601


@strawberry.type
class Project:
    """A top-level project container. Each project has one or more branches."""

    id: int
    name: str
    description: Optional[str]
    created_at: str  # ISO 8601
    branches: list[Branch] = strawberry.field(default_factory=list)


# -- Filter set types --


@strawberry.type
class FilterSetFilter:
    """A single filter within a filter set."""

    mode: str  # "class" | "attribute"
    ifc_class: Optional[str] = None
    attribute: Optional[str] = None
    value: Optional[str] = None


@strawberry.type
class FilterSet:
    """A named, persisted collection of filters scoped to a branch."""

    id: int
    branch_id: int
    name: str
    logic: str  # "AND" | "OR"
    filters: list[FilterSetFilter]
    created_at: str  # ISO 8601
    updated_at: str  # ISO 8601


@strawberry.type
class AppliedFilterSets:
    """The currently active filter sets for a branch."""

    filter_sets: list[FilterSet]
    combination_logic: str  # "AND" | "OR"


@strawberry.input
class FilterInput:
    """Input type for creating/updating individual filters in a filter set."""

    mode: str
    ifc_class: Optional[str] = None
    attribute: Optional[str] = None
    value: Optional[str] = None
