"""IFC relationship enums and element class enums for the GraphQL schema."""

from enum import Enum

import strawberry


@strawberry.enum(graphql_name_from="value")
class IfcRelationshipType(Enum):
    """IFC 4.3 objectified relationship types used as graph edge labels."""

    REL_AGGREGATES = "IfcRelAggregates"
    REL_CONTAINED_IN_SPATIAL = "IfcRelContainedInSpatialStructure"
    REL_CONNECTS_ELEMENTS = "IfcRelConnectsElements"
    REL_VOIDS_ELEMENT = "IfcRelVoidsElement"
    REL_FILLS_ELEMENT = "IfcRelFillsElement"
    REL_ASSOCIATES_MATERIAL = "IfcRelAssociatesMaterial"
    REL_DEFINES_BY_TYPE = "IfcRelDefinesByType"


@strawberry.enum
class IfcProductCategory(Enum):
    """Top-level IFC product categories for filtering."""

    ELEMENT = "IfcElement"
    SPATIAL_STRUCTURE_ELEMENT = "IfcSpatialStructureElement"
    SITE = "IfcSite"
    BUILDING = "IfcBuilding"
    BUILDING_STOREY = "IfcBuildingStorey"
    SPACE = "IfcSpace"
    WALL = "IfcWall"
    SLAB = "IfcSlab"
    BEAM = "IfcBeam"
    COLUMN = "IfcColumn"
    DOOR = "IfcDoor"
    WINDOW = "IfcWindow"
    ROOF = "IfcRoof"
    STAIR = "IfcStair"
    RAILING = "IfcRailing"
    COVERING = "IfcCovering"
    CURTAIN_WALL = "IfcCurtainWall"
    PLATE = "IfcPlate"
    MEMBER = "IfcMember"
    FOOTING = "IfcFooting"
    PILE = "IfcPile"
    DISTRIBUTION_ELEMENT = "IfcDistributionElement"
    FURNISHING_ELEMENT = "IfcFurnishingElement"
