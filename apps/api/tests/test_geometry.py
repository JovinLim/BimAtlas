"""Unit tests for IFC geometry extraction module.

Tests the geometry.py module functions that extract products from IFC files.
"""

import numpy as np
import pytest
import ifcopenshell

from src.services.ifc.geometry import (
    IfcProductRecord,
    extract_products,
    extract_products_from_model,
    _build_containment_map,
    _compute_content_hash,
    _extract_spatial_elements,
    _extract_geometric_elements,
)


class TestContentHash:
    """Test content hash computation."""
    
    def test_compute_content_hash_basic(self):
        """Test that content hash is computed correctly."""
        hash1 = _compute_content_hash(
            ifc_class="IfcWall",
            name="Wall-001",
            description="External wall",
            object_type="LoadBearing",
            tag="W1",
            contained_in="some-guid",
            vertices=b"vertices",
            normals=b"normals",
            faces=b"faces",
            matrix=b"matrix",
        )
        
        assert isinstance(hash1, str)
        assert len(hash1) == 64  # SHA-256 produces 64 hex characters
    
    def test_compute_content_hash_deterministic(self):
        """Test that same inputs produce same hash."""
        hash1 = _compute_content_hash(
            ifc_class="IfcWall",
            name="Wall-001",
            description=None,
            object_type=None,
            tag=None,
            contained_in=None,
            vertices=None,
            normals=None,
            faces=None,
            matrix=None,
        )
        
        hash2 = _compute_content_hash(
            ifc_class="IfcWall",
            name="Wall-001",
            description=None,
            object_type=None,
            tag=None,
            contained_in=None,
            vertices=None,
            normals=None,
            faces=None,
            matrix=None,
        )
        
        assert hash1 == hash2
    
    def test_compute_content_hash_different_for_different_inputs(self):
        """Test that different inputs produce different hashes."""
        hash1 = _compute_content_hash(
            ifc_class="IfcWall",
            name="Wall-001",
            description=None,
            object_type=None,
            tag=None,
            contained_in=None,
            vertices=None,
            normals=None,
            faces=None,
            matrix=None,
        )
        
        hash2 = _compute_content_hash(
            ifc_class="IfcWall",
            name="Wall-002",  # Different name
            description=None,
            object_type=None,
            tag=None,
            contained_in=None,
            vertices=None,
            normals=None,
            faces=None,
            matrix=None,
        )
        
        assert hash1 != hash2


class TestContainmentMap:
    """Test containment map building."""
    
    def test_build_containment_map(self, test_ifc_file):
        """Test that containment map is built correctly from IFC file."""
        model = ifcopenshell.open(str(test_ifc_file))
        containment_map = _build_containment_map(model)
        
        assert isinstance(containment_map, dict)
        # Should have some elements mapped to containers
        assert len(containment_map) > 0
        
        # All values should be valid GlobalIds (22 character strings)
        for element_gid, container_gid in containment_map.items():
            assert isinstance(element_gid, str)
            assert isinstance(container_gid, str)
            assert len(element_gid) == 22
            assert len(container_gid) == 22


class TestSpatialExtraction:
    """Test spatial element extraction."""
    
    def test_extract_spatial_elements(self, test_ifc_file):
        """Test extraction of spatial structure elements."""
        model = ifcopenshell.open(str(test_ifc_file))
        containment_map = _build_containment_map(model)
        
        spatial_records = _extract_spatial_elements(model, containment_map)
        
        assert isinstance(spatial_records, list)
        assert len(spatial_records) > 0
        
        # Check that we have expected spatial types
        spatial_classes = {r.ifc_class for r in spatial_records}
        expected_types = {"IfcProject", "IfcSite", "IfcBuilding", "IfcBuildingStorey"}
        assert spatial_classes & expected_types  # At least some overlap
        
        # All spatial elements should have NULL geometry
        for record in spatial_records:
            assert record.vertices is None
            assert record.normals is None
            assert record.faces is None
            assert record.matrix is None
            assert record.content_hash is not None
            assert len(record.global_id) == 22
    
    def test_spatial_elements_have_valid_structure(self, test_ifc_file):
        """Test that spatial elements have valid IfcProductRecord structure."""
        model = ifcopenshell.open(str(test_ifc_file))
        containment_map = _build_containment_map(model)
        
        spatial_records = _extract_spatial_elements(model, containment_map)
        
        for record in spatial_records:
            assert isinstance(record, IfcProductRecord)
            assert isinstance(record.global_id, str)
            assert isinstance(record.ifc_class, str)
            assert isinstance(record.content_hash, str)


class TestGeometricExtraction:
    """Test geometric element extraction."""
    
    def test_extract_geometric_elements(self, test_ifc_file):
        """Test extraction of elements with geometry."""
        model = ifcopenshell.open(str(test_ifc_file))
        containment_map = _build_containment_map(model)
        
        geometric_records = _extract_geometric_elements(model, containment_map)
        
        assert isinstance(geometric_records, list)
        assert len(geometric_records) > 0
        
        # All geometric elements should have geometry data
        for record in geometric_records:
            assert record.vertices is not None
            assert isinstance(record.vertices, bytes)
            assert len(record.vertices) > 0
            
            assert record.normals is not None
            assert isinstance(record.normals, bytes)
            
            assert record.faces is not None
            assert isinstance(record.faces, bytes)
            
            assert record.matrix is not None
            assert isinstance(record.matrix, bytes)
            
            assert record.content_hash is not None
            assert len(record.content_hash) == 64
    
    def test_geometric_elements_have_valid_arrays(self, test_ifc_file):
        """Test that geometry buffers can be deserialized back to numpy arrays."""
        model = ifcopenshell.open(str(test_ifc_file))
        containment_map = _build_containment_map(model)
        
        geometric_records = _extract_geometric_elements(model, containment_map)
        
        # Pick first record and verify buffers
        if geometric_records:
            record = geometric_records[0]
            
            # Vertices: float32 array, should be multiple of 3 (x, y, z)
            verts = np.frombuffer(record.vertices, dtype=np.float32)
            assert len(verts) % 3 == 0
            
            # Normals: float32 array, should be multiple of 3
            normals = np.frombuffer(record.normals, dtype=np.float32)
            assert len(normals) % 3 == 0
            
            # Faces: uint32 array, should be multiple of 3 (triangles)
            faces = np.frombuffer(record.faces, dtype=np.uint32)
            assert len(faces) % 3 == 0
            
            # Matrix: float64 array, should be 16 elements (4x4 matrix)
            matrix = np.frombuffer(record.matrix, dtype=np.float64)
            assert len(matrix) == 16


class TestFullExtraction:
    """Test full product extraction pipeline."""
    
    def test_extract_products_from_model(self, test_ifc_file):
        """Test extracting all products from an opened model."""
        model = ifcopenshell.open(str(test_ifc_file))
        records = extract_products_from_model(model)
        
        assert isinstance(records, list)
        assert len(records) > 0
        
        # Should have both spatial and geometric elements
        has_spatial = any(r.vertices is None for r in records)
        has_geometric = any(r.vertices is not None for r in records)
        
        assert has_spatial, "Should have spatial elements"
        assert has_geometric, "Should have geometric elements"
        
        # All records should have unique global_ids
        global_ids = [r.global_id for r in records]
        assert len(global_ids) == len(set(global_ids))
    
    def test_extract_products_from_path(self, test_ifc_file):
        """Test extracting products directly from file path."""
        records = extract_products(str(test_ifc_file))
        
        assert isinstance(records, list)
        assert len(records) > 0
        
        # Verify all records are valid
        for record in records:
            assert isinstance(record, IfcProductRecord)
            assert isinstance(record.global_id, str)
            assert len(record.global_id) == 22
            assert isinstance(record.ifc_class, str)
            assert isinstance(record.content_hash, str)
            assert len(record.content_hash) == 64
    
    def test_extract_products_expected_count(self, test_ifc_file):
        """Test that we extract the expected number of products from test file.
        
        According to test documentation, Ifc4_SampleHouse.ifc has 74 products.
        """
        records = extract_products(str(test_ifc_file))
        
        # Should extract approximately 74 products (might vary slightly)
        assert len(records) >= 70, f"Expected ~74 products, got {len(records)}"
        assert len(records) <= 80, f"Expected ~74 products, got {len(records)}"
    
    def test_extract_products_ifc_classes(self, test_ifc_file):
        """Test that we extract expected IFC classes."""
        records = extract_products(str(test_ifc_file))
        
        ifc_classes = {r.ifc_class for r in records}
        
        # Should have common IFC types
        expected_classes = {
            "IfcProject", "IfcSite", "IfcBuilding", "IfcBuildingStorey",
            "IfcWall", "IfcSlab", "IfcWindow", "IfcDoor"
        }
        
        # Check for overlap (not all may be present)
        overlap = expected_classes & ifc_classes
        assert len(overlap) >= 5, f"Expected common IFC classes, found: {ifc_classes}"


class TestErrorHandling:
    """Test error handling in geometry extraction."""
    
    def test_extract_products_invalid_path(self):
        """Test that invalid file path raises appropriate error."""
        with pytest.raises(Exception):  # ifcopenshell raises IOError or similar
            extract_products("/nonexistent/file.ifc")
    
    def test_extract_products_empty_model(self, tmp_path):
        """Test handling of minimal/empty IFC file."""
        # Create a minimal valid IFC file
        minimal_ifc = tmp_path / "minimal.ifc"
        minimal_ifc.write_text("""ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('ViewDefinition [CoordinationView]'),'2;1');
FILE_NAME('minimal.ifc','2024-01-01T00:00:00',(''),(''),('IfcOpenShell'),'IfcOpenShell','');
FILE_SCHEMA(('IFC4'));
ENDSEC;
DATA;
#1=IFCPROJECT('0000000000000000000001',$,'Test',$,$,$,$,$,$);
ENDSEC;
END-ISO-10303-21;
""")
        
        records = extract_products(str(minimal_ifc))
        
        # Should at least extract the project
        assert len(records) >= 1
        assert any(r.ifc_class == "IfcProject" for r in records)
