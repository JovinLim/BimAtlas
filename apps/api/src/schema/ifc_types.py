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
from strawberry.scalars import JSON

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
class IfcShapeRepresentation:
    """Synthetic entity representing a single shape representation for a product.

    Backed by rows in ``ifc_entity`` with ``ifc_class = 'IfcShapeRepresentation'``
    and geometry stored on the shape rep rather than the product.
    """

    global_id: str
    representation_identifier: Optional[str] = None
    representation_type: Optional[str] = None
    mesh: Optional[IfcMeshRepresentation] = None


@strawberry.type
class IfcRelatedProduct:
    """A related product reached via an IFC objectified relationship edge."""

    global_id: str
    ifc_class: str
    name: Optional[str] = None
    relationship: IfcRelationshipType


@strawberry.type
class IfcRelationEdge:
    """A graph edge between two products (or type/shape entities)."""

    source_id: str
    source_ifc_class: str
    source_name: Optional[str] = None
    target_id: str
    target_ifc_class: str
    target_name: Optional[str] = None
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
    predefined_type: Optional[str] = None
    representations: list[IfcShapeRepresentation] = strawberry.field(default_factory=list)
    property_sets: Optional[JSON] = None
    attributes: Optional[JSON] = None


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


@strawberry.type
class IfcProductClassNode:
    """A node in the IFC product class hierarchy used for filters."""

    ifc_class: str
    children: list["IfcProductClassNode"] = strawberry.field(default_factory=list)


# -- Versioning types --


@strawberry.enum
class ChangeType(Enum):
    ADDED = "ADDED"
    MODIFIED = "MODIFIED"
    DELETED = "DELETED"


@strawberry.type
class Revision:
    id: str
    branch_id: str
    revision_seq: int  # monotonic sequence for ordering and querying at revision
    label: Optional[str]
    ifc_filename: Optional[str]
    author_id: Optional[str]
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

    id: str
    project_id: str
    name: str
    created_at: str  # ISO 8601


@strawberry.type
class Project:
    """A top-level project container. Each project has one or more branches."""

    id: str
    name: str
    description: Optional[str]
    created_at: str  # ISO 8601
    branches: list[Branch] = strawberry.field(default_factory=list)


# -- Filter set types --


@strawberry.type
class FilterSetFilter:
    """A single filter within a filter set."""

    mode: str  # "class" | "attribute" | "relation"
    ifc_class: Optional[str] = None
    attribute: Optional[str] = None
    value: Optional[str] = None
    relation: Optional[str] = None
    operator: Optional[str] = None  # e.g. is, contains, inherits_from, gt
    value_type: Optional[str] = None  # "string" | "numeric" for attribute mode
    # Relation mode: filter the related entity
    relation_target_class: Optional[str] = None
    relation_target_attribute: Optional[str] = None
    relation_target_operator: Optional[str] = None
    relation_target_value: Optional[str] = None
    relation_target_value_type: Optional[str] = None


@strawberry.type
class FilterSet:
    """A named, persisted collection of filters scoped to a branch."""

    id: str
    branch_id: str
    name: str
    logic: str  # "AND" | "OR" (deprecated: use filters_tree.op)
    filters: list[FilterSetFilter]  # Flattened for backward compat
    filters_tree: Optional[JSON] = None  # Canonical nested Match ALL/ANY tree
    color: str  # hex color, e.g. "#4A90D9"
    created_at: str  # ISO 8601
    updated_at: str  # ISO 8601


@strawberry.type
class AppliedFilterSets:
    """The currently active filter sets for a branch."""

    filter_sets: list[FilterSet]
    combination_logic: str  # "AND" | "OR"


@strawberry.type
class FilterSetMatch:
    """Per-filter-set entity matches for coloring."""

    filter_set_id: str
    color: str
    global_ids: list[str]


@strawberry.input
class FilterInput:
    """Input type for creating/updating individual filters in a filter set."""

    mode: str
    ifc_class: Optional[str] = None
    attribute: Optional[str] = None
    value: Optional[str] = None
    relation: Optional[str] = None
    operator: Optional[str] = None  # e.g. is, contains, inherits_from, gt
    value_type: Optional[str] = None  # "string" | "numeric" for attribute mode
    # Relation mode: filter the related entity (e.g. class IFCBuildingStorey, Name="Ground Floor")
    relation_target_class: Optional[str] = None
    relation_target_attribute: Optional[str] = None
    relation_target_operator: Optional[str] = None
    relation_target_value: Optional[str] = None
    relation_target_value_type: Optional[str] = None


# -- Sheet template types (FEAT-003 table page bottom-sheet persistence) --


@strawberry.type
class SheetTemplate:
    """A project-scoped saved bottom-sheet table state."""

    id: str
    project_id: str
    name: str
    sheet: strawberry.scalars.JSON
    open: bool
    created_at: str
    updated_at: str


# -- Saved views (BCF-compliant) --------------------------------------------


@strawberry.type
class SavedView:
    """A BCF-compliant saved view with camera, clipping, and linked filter sets."""

    id: str
    branch_id: str
    name: str
    bcf_camera_state: strawberry.scalars.JSON
    ui_filters: strawberry.scalars.JSON
    filter_sets: list["FilterSet"] = strawberry.field(default_factory=list)
    created_at: str
    updated_at: str


# -- Validation types (FEAT-004) -------------------------------------------


@strawberry.type
class UploadedSchema:
    """An IFC schema uploaded via POST /ifc-schema, stored in ifc_schema + validation_rule."""

    id: str  # schema_id UUID
    version_name: str
    rule_count: int
    project_ids: list[str] = strawberry.field(default_factory=list)


@strawberry.type
class UploadedSchemaRule:
    """A validation rule from an uploaded IFC schema (validation_rule table)."""

    rule_id: str
    name: str
    description: Optional[str] = None
    target_ifc_class: str
    effective_required_attributes: Optional[str] = None  # JSON string, only for required_attributes rules
    rule_schema_json: Optional[str] = None  # Full rule_schema for edit
    display_severity: str  # "Required" or "Info" - Required when required: true, else Info
    severity: str  # Original DB severity (kept for compatibility)


@strawberry.type
class ValidationViolation:
    """A single entity violating a rule."""

    global_id: str
    ifc_class: str
    message: str


@strawberry.type
class ValidationRuleResult:
    """Result of evaluating a single rule."""

    rule_global_id: str
    rule_name: str
    severity: str
    passed: bool
    violations: list[ValidationViolation] = strawberry.field(default_factory=list)


@strawberry.type
class ValidationRunResultType:
    """Result of a full validation run."""

    schema_global_id: str
    schema_name: str
    branch_id: str
    revision_seq: int
    results: list[ValidationRuleResult] = strawberry.field(default_factory=list)
    error_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    passed_count: int = 0


