"""Reusable Cypher query templates for the AGE graph.

Templates use :func:`str.format` placeholders:

- ``{global_id}``    -- IFC GlobalId (pre-validated for safe embedding)
- ``{n_filter}``     -- revision-scoped WHERE clause for node alias ``n``
- ``{r_filter}``     -- same for relationship alias ``r``
- ``{m_filter}``     -- same for neighbor alias ``m``
- etc.

Literal Cypher braces are escaped as ``{{`` and ``}}``.
"""

# ---------------------------------------------------------------------------
# Neighbors (all relationship types)
# ---------------------------------------------------------------------------

NEIGHBORS_OUT = (
    "MATCH (n {{global_id: '{global_id}'}})-[r]->(m) "
    "WHERE {n_filter} AND {r_filter} AND {m_filter} "
    "RETURN m.global_id AS gid, label(m) AS lbl, m.name AS name, type(r) AS rel"
)

NEIGHBORS_IN = (
    "MATCH (n {{global_id: '{global_id}'}})<-[r]-(m) "
    "WHERE {n_filter} AND {r_filter} AND {m_filter} "
    "RETURN m.global_id AS gid, label(m) AS lbl, m.name AS name, type(r) AS rel"
)

# ---------------------------------------------------------------------------
# Spatial decomposition tree
# ---------------------------------------------------------------------------

# Root spatial nodes (IfcProject) visible at a given revision.
SPATIAL_ROOTS = (
    "MATCH (p:IfcProject) "
    "WHERE {p_filter} "
    "RETURN p.global_id AS gid, label(p) AS lbl, p.name AS name"
)

# Direct children of a spatial node via IfcRelAggregates.
SPATIAL_CHILDREN = (
    "MATCH (parent {{global_id: '{global_id}'}})"
    "-[r:IfcRelAggregates]->(child) "
    "WHERE {parent_filter} AND {r_filter} AND {child_filter} "
    "RETURN child.global_id AS gid, label(child) AS lbl, child.name AS name"
)

# Elements contained in a spatial structure via IfcRelContainedInSpatialStructure.
# Edge direction: element -> spatial container (as per the ingestion model).
CONTAINED_ELEMENTS = (
    "MATCH (spatial {{global_id: '{global_id}'}})"
    "<-[r:IfcRelContainedInSpatialStructure]-(elem) "
    "WHERE {spatial_filter} AND {r_filter} AND {elem_filter} "
    "RETURN elem.global_id AS gid, label(elem) AS lbl, elem.name AS name"
)
