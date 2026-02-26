"""IfcOpenShell mesh extraction, triangulation, and binary serialization.

Uses ``ifcopenshell.geom`` to extract triangulated meshes from every
``IfcProduct`` in an IFC file and serialize vertex/normal/face buffers to raw
bytes suitable for Postgres BYTEA storage.

The returned ``IfcProductRecord`` maps 1-to-1 to an ``ifc_products`` row and
includes a ``content_hash`` (SHA-256) used for SCD Type 2 change detection
during versioned ingestion.
"""

from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import dataclass
from typing import Any

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.element
import numpy as np


@dataclass
class IfcEntityRecord:
    """Maps 1:1 to an ifc_entity row, using IFC 4.3 attribute names."""

    ifc_global_id: str  # IfcRoot.GlobalId (stable across revisions)
    ifc_class: str  # e.g. "IfcWall", "IfcBuildingStorey"
    attributes: dict[str, Any]  # Flattened EXPRESS attributes / metadata
    geometry: bytes | None  # Packed geometry blob (may be NULL for spatial elements)
    content_hash: str  # SHA-256 of (ifc_class, attributes, geometry)
    # Used for SCD2 change detection during versioned ingestion


def _compute_content_hash(
    ifc_class: str,
    attributes: dict[str, Any],
    geometry: bytes | None,
) -> str:
    """Compute a SHA-256 content hash over mutable fields for change detection."""
    h = hashlib.sha256()
    h.update(ifc_class.encode("utf-8"))
    attrs_json = json.dumps(attributes or {}, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    h.update(attrs_json)
    h.update(geometry or b"")
    return h.hexdigest()


def _pack_geometry(
    vertices: bytes | None,
    normals: bytes | None,
    faces: bytes | None,
    matrix: bytes | None,
) -> bytes | None:
    """Pack separate geometry buffers into a single BYTEA blob.

    Format: four big-endian uint64 lengths (vertices, normals, faces, matrix)
    followed by the raw buffers in order. A length of 0 means the buffer is
    absent. Matches _unpack_geometry in schema/queries.py.
    """
    if not any((vertices, normals, faces, matrix)):
        return None

    lengths = [
        len(vertices) if vertices else 0,
        len(normals) if normals else 0,
        len(faces) if faces else 0,
        len(matrix) if matrix else 0,
    ]
    header = b"".join(struct.pack(">Q", n) for n in lengths)
    buffers = [b for b in (vertices, normals, faces, matrix) if b]
    return header + b"".join(buffers)


def _build_containment_map(model: ifcopenshell.file) -> dict[str, str]:
    """Build a mapping from element GlobalId -> spatial container GlobalId.

    Parses all ``IfcRelContainedInSpatialStructure`` relationships. Per IFC 4.3
    sec 4.1.5.13, a physical element shall only be contained within a **single**
    spatial structure element (IfcBuildingStorey being the default container).
    """
    containment: dict[str, str] = {}
    for rel in model.by_type("IfcRelContainedInSpatialStructure"):
        container = rel.RelatingStructure
        if container is None:
            continue
        container_gid = container.GlobalId
        for element in rel.RelatedElements:
            containment[element.GlobalId] = container_gid
    return containment


def _extract_spatial_elements(
    model: ifcopenshell.file,
    containment_map: dict[str, str],
) -> list[IfcEntityRecord]:
    """Extract spatial structure elements (no geometry).

    Parses IfcSpatialStructureElement subtypes: IfcProject, IfcSite,
    IfcBuilding, IfcBuildingStorey, IfcSpace. These are stored as rows
    with NULL geometry columns.
    """
    records: list[IfcEntityRecord] = []
    spatial_types = (
        "IfcProject",
        "IfcSite",
        "IfcBuilding",
        "IfcBuildingStorey",
        "IfcSpace",
    )

    seen_gids: set[str] = set()
    for spatial_type in spatial_types:
        for element in model.by_type(spatial_type):
            gid = element.GlobalId
            if gid in seen_gids:
                continue
            seen_gids.add(gid)

            ifc_class = element.is_a()
            name = getattr(element, "Name", None)
            description = getattr(element, "Description", None)
            object_type = getattr(element, "ObjectType", None)
            tag = getattr(element, "Tag", None)
            contained_in = containment_map.get(gid)

            attributes: dict[str, Any] = {
                "Name": name,
                "Description": description,
                "ObjectType": object_type,
                "Tag": tag,
            }
            if contained_in is not None:
                attributes["ContainedIn"] = contained_in

            geometry_blob = None
            content_hash = _compute_content_hash(
                ifc_class=ifc_class,
                attributes=attributes,
                geometry=geometry_blob,
            )

            records.append(
                IfcEntityRecord(
                    ifc_global_id=gid,
                    ifc_class=ifc_class,
                    attributes=attributes,
                    geometry=geometry_blob,
                    content_hash=content_hash,
                )
            )
    return records


def _extract_geometric_elements(
    model: ifcopenshell.file,
    containment_map: dict[str, str],
) -> list[IfcEntityRecord]:
    """Extract all IfcProduct entities that have geometry.

    Uses ``ifcopenshell.geom.iterator`` to triangulate meshes in world
    coordinates (``USE_WORLD_COORDS = True``), then serializes vertex, normal,
    face, and transformation matrix buffers to raw bytes.
    """
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)

    iterator = ifcopenshell.geom.iterator(settings, model)
    records: list[IfcEntityRecord] = []

    if not iterator.initialize():
        return records

    while True:
        shape = iterator.get()
        element = model.by_id(shape.id)

        gid = element.GlobalId
        ifc_class = element.is_a()
        name = getattr(element, "Name", None)
        description = getattr(element, "Description", None)
        object_type = getattr(element, "ObjectType", None)
        tag = getattr(element, "Tag", None)
        contained_in = containment_map.get(gid)

        attributes: dict[str, Any] = {
            "Name": name,
            "Description": description,
            "ObjectType": object_type,
            "Tag": tag,
        }
        if contained_in is not None:
            attributes["ContainedIn"] = contained_in

        # Triangulated mesh buffers
        verts = np.array(shape.geometry.verts, dtype=np.float32)
        faces = np.array(shape.geometry.faces, dtype=np.uint32)
        normals = np.array(shape.geometry.normals, dtype=np.float32)
        # shape.transformation.matrix is already a tuple/sequence, no need for .data
        matrix_data = shape.transformation.matrix.data if hasattr(shape.transformation.matrix, 'data') else shape.transformation.matrix
        matrix = np.array(matrix_data, dtype=np.float64)

        verts_bytes = verts.tobytes()
        normals_bytes = normals.tobytes()
        faces_bytes = faces.tobytes()
        matrix_bytes = matrix.tobytes()

        geometry_blob = _pack_geometry(
            vertices=verts_bytes,
            normals=normals_bytes,
            faces=faces_bytes,
            matrix=matrix_bytes,
        )

        content_hash = _compute_content_hash(
            ifc_class=ifc_class,
            attributes=attributes,
            geometry=geometry_blob,
        )

        records.append(
            IfcEntityRecord(
                ifc_global_id=gid,
                ifc_class=ifc_class,
                attributes=attributes,
                geometry=geometry_blob,
                content_hash=content_hash,
            )
        )

        if not iterator.next():
            break

    return records


def extract_products_from_model(model: ifcopenshell.file) -> list[IfcEntityRecord]:
    """Extract all products from an already-opened IFC model.

    Implements the two-phase extraction described in the plan:

    **Phase 1 -- Spatial structure:** Parse every ``IfcSpatialStructureElement``
    (IfcProject, IfcSite, IfcBuilding, IfcBuildingStorey, IfcSpace) and return
    records with NULL geometry.

    **Phase 2 -- Elements with geometry:** Iterate all ``IfcProduct`` entities
    via the geometry iterator, triangulate meshes in world coordinates, and
    return records with serialized binary buffers.

    Containment is resolved from ``IfcRelContainedInSpatialStructure``
    relationships. Per IFC 4.3 sec 4.1.5.13, a physical element shall only be
    contained within a single spatial structure element.

    Args:
        model: An already-opened ``ifcopenshell.file`` object.

    Returns:
        A list of ``IfcProductRecord`` instances ready for database insertion.
        Spatial elements come first, followed by geometric elements.
    """
    # Build containment map: element GlobalId -> container GlobalId
    containment_map = _build_containment_map(model)

    # Phase 1: Spatial structure elements (no geometry)
    spatial_records = _extract_spatial_elements(model, containment_map)

    # Phase 2: Elements with geometry
    geometric_records = _extract_geometric_elements(model, containment_map)

    # Merge: spatial elements first, then geometric elements (skip duplicates
    # where a spatial element also has geometry -- the geometric version wins)
    records: list[IfcEntityRecord] = []
    geometric_gids = {r.ifc_global_id for r in geometric_records}

    # Add spatial-only records (those without geometry from the iterator)
    for rec in spatial_records:
        if rec.ifc_global_id not in geometric_gids:
            records.append(rec)

    # Add all geometric records
    records.extend(geometric_records)

    return records


def extract_products(ifc_path: str) -> list[IfcEntityRecord]:
    """Parse an IFC file and extract all products as DB-ready records.

    Convenience wrapper around :func:`extract_products_from_model` that opens
    the IFC file from a filesystem path.

    Args:
        ifc_path: Filesystem path to the IFC file.

    Returns:
        A list of ``IfcEntityRecord`` instances ready for database insertion.
        Spatial elements come first, followed by geometric elements.
    """
    model = ifcopenshell.open(ifc_path)
    return extract_products_from_model(model)
