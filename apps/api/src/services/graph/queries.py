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
    "MATCH (n {{ifc_global_id: '{global_id}'}})-[r]->(m) "
    "WHERE {n_filter} AND {r_filter} AND {m_filter} "
    "RETURN m.ifc_global_id AS gid, label(m) AS lbl, m.name AS name, type(r) AS rel"
)

NEIGHBORS_IN = (
    "MATCH (n {{ifc_global_id: '{global_id}'}})<-[r]-(m) "
    "WHERE {n_filter} AND {r_filter} AND {m_filter} "
    "RETURN m.ifc_global_id AS gid, label(m) AS lbl, m.name AS name, type(r) AS rel"
)

# ---------------------------------------------------------------------------
# Products by relation type
# ---------------------------------------------------------------------------

PRODUCTS_BY_RELATION = (
    "MATCH (n)-[r:{rel_type}]-(m) "
    "WHERE {r_filter} AND {n_filter} "
    "RETURN DISTINCT n.ifc_global_id AS gid"
)

# Products that have relation to any of the target GIDs (returns the "other" endpoint).
PRODUCTS_RELATED_TO_TARGETS = (
    "MATCH (n)-[r:{rel_type}]-(m) "
    "WHERE {r_filter} AND {n_filter} AND {m_filter} AND m.ifc_global_id IN {target_gids} "
    "RETURN DISTINCT n.ifc_global_id AS gid"
)

# ---------------------------------------------------------------------------
# Spatial decomposition tree
# ---------------------------------------------------------------------------

# Root spatial nodes (IfcProject) visible at a given revision.
SPATIAL_ROOTS = (
    "MATCH (p:IfcProject) "
    "WHERE {p_filter} "
    "RETURN p.ifc_global_id AS gid, label(p) AS lbl, p.name AS name"
)

# Direct children of a spatial node via IfcRelAggregates.
SPATIAL_CHILDREN = (
    "MATCH (parent {{ifc_global_id: '{global_id}'}})"
    "-[r:IfcRelAggregates]->(child) "
    "WHERE {parent_filter} AND {r_filter} AND {child_filter} "
    "RETURN child.ifc_global_id AS gid, label(child) AS lbl, child.name AS name"
)

# Elements contained in a spatial structure via IfcRelContainedInSpatialStructure.
# Edge direction: element -> spatial container (as per the ingestion model).
CONTAINED_ELEMENTS = (
    "MATCH (spatial {{ifc_global_id: '{global_id}'}})"
    "<-[r:IfcRelContainedInSpatialStructure]-(elem) "
    "WHERE {spatial_filter} AND {r_filter} AND {elem_filter} "
    "RETURN elem.ifc_global_id AS gid, label(elem) AS lbl, elem.name AS name"
)

# ---------------------------------------------------------------------------
# Element-level relations (non-spatial)
# ---------------------------------------------------------------------------

ELEMENT_RELATIONS = (
    "MATCH (a)-[r]->(b) "
    "WHERE {a_filter} AND {r_filter} AND {b_filter} AND {rel_type_filter} "
    "RETURN a.ifc_global_id AS src, label(a) AS src_lbl, a.name AS src_name, "
    "b.ifc_global_id AS dst, label(b) AS dst_lbl, b.name AS dst_name, type(r) AS rel"
)

# ---------------------------------------------------------------------------
# Validation schema management
# ---------------------------------------------------------------------------

RULES_FOR_SCHEMA = (
    "MATCH (schema {{ifc_global_id: '{schema_gid}'}})"
    "<-[r:IfcRelValidationToSchema]-(rule) "
    "WHERE {schema_filter} AND {r_filter} AND {rule_filter} "
    "RETURN rule.ifc_global_id AS gid"
)

SCHEMA_FOR_RULE = (
    "MATCH (rule {{ifc_global_id: '{rule_gid}'}})"
    "-[r:IfcRelValidationToSchema]->(schema) "
    "WHERE {rule_filter} AND {r_filter} AND {schema_filter} "
    "RETURN schema.ifc_global_id AS gid"
)

# ---------------------------------------------------------------------------
# Subgraph validation scoping queries
# ---------------------------------------------------------------------------

ENTITIES_IN_SPATIAL_SCOPE = (
    "MATCH (spatial {{ifc_global_id: '{scope_gid}'}})"
    "<-[r:IfcRelContainedInSpatialStructure]-(elem) "
    "WHERE {spatial_filter} AND {r_filter} AND {elem_filter} "
    "RETURN elem.ifc_global_id AS gid"
)

ENTITIES_IN_SPATIAL_SCOPE_BY_NAME = (
    "MATCH (spatial {{name: '{scope_name}'}})"
    "<-[r:IfcRelContainedInSpatialStructure]-(elem) "
    "WHERE {spatial_filter} AND {r_filter} AND {elem_filter} "
    "RETURN elem.ifc_global_id AS gid"
)

ENTITIES_IN_AGGREGATE_SCOPE = (
    "MATCH (parent {{ifc_global_id: '{parent_gid}'}})"
    "-[r:IfcRelAggregates]->(child) "
    "WHERE {parent_filter} AND {r_filter} AND {child_filter} "
    "RETURN child.ifc_global_id AS gid"
)

ENTITIES_CONNECTED_VIA = (
    "MATCH (source {{ifc_global_id: '{source_gid}'}})"
    "-[r:{rel_type}]-(target) "
    "WHERE {source_filter} AND {r_filter} AND {target_filter} "
    "RETURN target.ifc_global_id AS gid"
)
