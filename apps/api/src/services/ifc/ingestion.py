"""Orchestrates IFC parse -> DB insert (versioned ingestion pipeline).

Implements the two-phase, diff-aware ingestion described in the plan:
  Phase 1: Spatial structure (IfcSpatialStructureElement hierarchy)
  Phase 2: Elements with containment and geometry
"""

# TODO: Implement versioned ingestion pipeline
