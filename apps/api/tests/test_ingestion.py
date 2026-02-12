"""Unit tests for IFC ingestion module.

Tests the ingestion.py module which orchestrates the diff-aware versioned
ingestion pipeline.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from src.services.ifc.ingestion import (
    ingest_ifc,
    IngestionResult,
    IfcRelationshipRecord,
    _extract_relationships,
    _diff_products,
    _create_revision,
    _load_current_hashes,
    _close_product_rows,
    _insert_product_rows,
)
from src.services.ifc.geometry import IfcProductRecord


class TestRelationshipExtraction:
    """Test IFC relationship extraction."""
    
    def test_extract_relationships_from_real_file(self, test_ifc_file):
        """Test extracting relationships from real IFC file."""
        import ifcopenshell
        model = ifcopenshell.open(str(test_ifc_file))
        
        relationships = _extract_relationships(model)
        
        assert isinstance(relationships, list)
        assert len(relationships) > 0
        
        # Verify relationship structure
        for rel in relationships:
            assert isinstance(rel, IfcRelationshipRecord)
            assert isinstance(rel.from_global_id, str)
            assert isinstance(rel.to_global_id, str)
            assert isinstance(rel.relationship_type, str)
            assert len(rel.from_global_id) == 22
            assert len(rel.to_global_id) == 22
    
    def test_extract_relationships_types(self, test_ifc_file):
        """Test that we extract expected relationship types."""
        import ifcopenshell
        model = ifcopenshell.open(str(test_ifc_file))
        
        relationships = _extract_relationships(model)
        
        rel_types = {r.relationship_type for r in relationships}
        
        # Should have common relationship types
        expected_types = {
            "IfcRelAggregates",
            "IfcRelContainedInSpatialStructure"
        }
        
        overlap = expected_types & rel_types
        assert len(overlap) >= 1, f"Expected relationship types, found: {rel_types}"


class TestDiffEngine:
    """Test product diffing logic."""
    
    def test_diff_products_all_added(self):
        """Test diff when all products are new."""
        new_records = [
            IfcProductRecord(
                global_id="0000000000000000000001",
                ifc_class="IfcWall",
                name="Wall-1",
                description=None,
                object_type=None,
                tag=None,
                contained_in=None,
                vertices=None,
                normals=None,
                faces=None,
                matrix=None,
                content_hash="hash1",
            ),
            IfcProductRecord(
                global_id="0000000000000000000002",
                ifc_class="IfcSlab",
                name="Slab-1",
                description=None,
                object_type=None,
                tag=None,
                contained_in=None,
                vertices=None,
                normals=None,
                faces=None,
                matrix=None,
                content_hash="hash2",
            ),
        ]
        
        current_hashes = {}  # Empty - no existing products
        
        added, modified, deleted_gids, unchanged_gids = _diff_products(
            new_records, current_hashes
        )
        
        assert len(added) == 2
        assert len(modified) == 0
        assert len(deleted_gids) == 0
        assert len(unchanged_gids) == 0
        
        assert added[0].global_id in ["0000000000000000000001", "0000000000000000000002"]
    
    def test_diff_products_all_unchanged(self):
        """Test diff when all products are unchanged."""
        new_records = [
            IfcProductRecord(
                global_id="0000000000000000000001",
                ifc_class="IfcWall",
                name="Wall-1",
                description=None,
                object_type=None,
                tag=None,
                contained_in=None,
                vertices=None,
                normals=None,
                faces=None,
                matrix=None,
                content_hash="hash1",
            ),
        ]
        
        current_hashes = {"0000000000000000000001": "hash1"}
        
        added, modified, deleted_gids, unchanged_gids = _diff_products(
            new_records, current_hashes
        )
        
        assert len(added) == 0
        assert len(modified) == 0
        assert len(deleted_gids) == 0
        assert len(unchanged_gids) == 1
        assert "0000000000000000000001" in unchanged_gids
    
    def test_diff_products_modified(self):
        """Test diff when products are modified."""
        new_records = [
            IfcProductRecord(
                global_id="0000000000000000000001",
                ifc_class="IfcWall",
                name="Wall-1-Updated",  # Name changed
                description=None,
                object_type=None,
                tag=None,
                contained_in=None,
                vertices=None,
                normals=None,
                faces=None,
                matrix=None,
                content_hash="hash1_new",  # Different hash
            ),
        ]
        
        current_hashes = {"0000000000000000000001": "hash1_old"}
        
        added, modified, deleted_gids, unchanged_gids = _diff_products(
            new_records, current_hashes
        )
        
        assert len(added) == 0
        assert len(modified) == 1
        assert len(deleted_gids) == 0
        assert len(unchanged_gids) == 0
        assert modified[0].global_id == "0000000000000000000001"
    
    def test_diff_products_deleted(self):
        """Test diff when products are deleted."""
        new_records = []  # No products in new model
        
        current_hashes = {
            "0000000000000000000001": "hash1",
            "0000000000000000000002": "hash2",
        }
        
        added, modified, deleted_gids, unchanged_gids = _diff_products(
            new_records, current_hashes
        )
        
        assert len(added) == 0
        assert len(modified) == 0
        assert len(deleted_gids) == 2
        assert len(unchanged_gids) == 0
        assert "0000000000000000000001" in deleted_gids
        assert "0000000000000000000002" in deleted_gids
    
    def test_diff_products_mixed(self):
        """Test diff with mixed changes."""
        new_records = [
            # Unchanged
            IfcProductRecord(
                global_id="0000000000000000000001",
                ifc_class="IfcWall",
                name="Wall-1",
                description=None,
                object_type=None,
                tag=None,
                contained_in=None,
                vertices=None,
                normals=None,
                faces=None,
                matrix=None,
                content_hash="hash1",
            ),
            # Modified
            IfcProductRecord(
                global_id="0000000000000000000002",
                ifc_class="IfcSlab",
                name="Slab-1-Updated",
                description=None,
                object_type=None,
                tag=None,
                contained_in=None,
                vertices=None,
                normals=None,
                faces=None,
                matrix=None,
                content_hash="hash2_new",
            ),
            # Added
            IfcProductRecord(
                global_id="0000000000000000000004",
                ifc_class="IfcDoor",
                name="Door-1",
                description=None,
                object_type=None,
                tag=None,
                contained_in=None,
                vertices=None,
                normals=None,
                faces=None,
                matrix=None,
                content_hash="hash4",
            ),
        ]
        
        current_hashes = {
            "0000000000000000000001": "hash1",  # Unchanged
            "0000000000000000000002": "hash2_old",  # Modified
            "0000000000000000000003": "hash3",  # Deleted
        }
        
        added, modified, deleted_gids, unchanged_gids = _diff_products(
            new_records, current_hashes
        )
        
        assert len(added) == 1
        assert len(modified) == 1
        assert len(deleted_gids) == 1
        assert len(unchanged_gids) == 1
        
        assert added[0].global_id == "0000000000000000000004"
        assert modified[0].global_id == "0000000000000000000002"
        assert "0000000000000000000003" in deleted_gids
        assert "0000000000000000000001" in unchanged_gids


class TestDatabaseOperations:
    """Test database operations during ingestion."""
    
    def test_create_revision(self, db_pool, clean_db):
        """Test creating a new revision."""
        from src.db import get_conn, put_conn
        
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                rev_id = _create_revision(cur, "test.ifc", "Test revision")
                conn.commit()
            
            # Verify revision was created
            with conn.cursor() as cur:
                cur.execute("SELECT id, label, ifc_filename FROM revisions WHERE id = %s", (rev_id,))
                row = cur.fetchone()
            
            assert row is not None
            assert row[0] == rev_id
            assert row[1] == "Test revision"
            assert row[2] == "test.ifc"
        finally:
            put_conn(conn)
    
    def test_load_current_hashes_empty(self, db_pool, clean_db):
        """Test loading hashes when database is empty."""
        from src.db import get_conn, put_conn
        
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                hashes = _load_current_hashes(cur)
            
            assert isinstance(hashes, dict)
            assert len(hashes) == 0
        finally:
            put_conn(conn)
    
    def test_insert_product_rows(self, db_pool, clean_db):
        """Test inserting product rows."""
        from src.db import get_conn, put_conn
        
        conn = get_conn()
        try:
            # Create revision first
            with conn.cursor() as cur:
                rev_id = _create_revision(cur, "test.ifc", None)
                conn.commit()
            
            # Insert products
            records = [
                IfcProductRecord(
                    global_id="0000000000000000000001",
                    ifc_class="IfcWall",
                    name="Wall-1",
                    description=None,
                    object_type=None,
                    tag=None,
                    contained_in=None,
                    vertices=None,
                    normals=None,
                    faces=None,
                    matrix=None,
                    content_hash="hash1",
                ),
            ]
            
            with conn.cursor() as cur:
                _insert_product_rows(cur, records, rev_id)
                conn.commit()
            
            # Verify products were inserted
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM ifc_products WHERE valid_from_rev = %s", (rev_id,))
                count = cur.fetchone()[0]
            
            assert count == 1
        finally:
            put_conn(conn)
    
    def test_close_product_rows(self, db_pool, clean_db):
        """Test closing product rows (SCD Type 2)."""
        from src.db import get_conn, put_conn
        
        conn = get_conn()
        try:
            # Create first revision and insert product
            with conn.cursor() as cur:
                rev_id_1 = _create_revision(cur, "test_v1.ifc", None)
                conn.commit()
            
            records = [
                IfcProductRecord(
                    global_id="0000000000000000000001",
                    ifc_class="IfcWall",
                    name="Wall-1",
                    description=None,
                    object_type=None,
                    tag=None,
                    contained_in=None,
                    vertices=None,
                    normals=None,
                    faces=None,
                    matrix=None,
                    content_hash="hash1",
                ),
            ]
            
            with conn.cursor() as cur:
                _insert_product_rows(cur, records, rev_id_1)
                conn.commit()
            
            # Create second revision and close the product
            with conn.cursor() as cur:
                rev_id_2 = _create_revision(cur, "test_v2.ifc", None)
                conn.commit()
            
            with conn.cursor() as cur:
                _close_product_rows(cur, ["0000000000000000000001"], rev_id_2)
                conn.commit()
            
            # Verify product was closed
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT valid_to_rev FROM ifc_products WHERE global_id = %s",
                    ("0000000000000000000001",)
                )
                row = cur.fetchone()
            
            assert row is not None
            assert row[0] == rev_id_2
        finally:
            put_conn(conn)


class TestFullIngestion:
    """Test full ingestion pipeline."""
    
    def test_ingest_ifc_first_import(self, db_pool, age_graph, test_ifc_file):
        """Test ingesting IFC file for the first time."""
        result = ingest_ifc(str(test_ifc_file), label="Initial import")
        
        assert isinstance(result, IngestionResult)
        assert result.revision_id == 1
        assert result.total_products > 0
        assert result.added == result.total_products  # All products are added
        assert result.modified == 0
        assert result.deleted == 0
        assert result.unchanged == 0
        assert result.edges_created >= 0
    
    def test_ingest_ifc_second_import_unchanged(self, db_pool, age_graph, test_ifc_file):
        """Test importing same IFC file twice (all unchanged)."""
        # First import
        result1 = ingest_ifc(str(test_ifc_file), label="Import 1")
        
        # Second import (same file)
        result2 = ingest_ifc(str(test_ifc_file), label="Import 2")
        
        assert result2.revision_id == 2
        assert result2.total_products == result1.total_products
        assert result2.added == 0
        assert result2.modified == 0
        assert result2.deleted == 0
        assert result2.unchanged == result1.total_products
    
    def test_ingest_ifc_creates_database_records(self, db_pool, age_graph, test_ifc_file):
        """Test that ingestion creates correct database records."""
        from src.db import get_conn, put_conn
        
        result = ingest_ifc(str(test_ifc_file), label="Test import")
        
        conn = get_conn()
        try:
            # Check revision was created
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM revisions")
                rev_count = cur.fetchone()[0]
            assert rev_count == 1
            
            # Check products were inserted
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM ifc_products WHERE valid_to_rev IS NULL")
                product_count = cur.fetchone()[0]
            assert product_count == result.total_products
            
            # Check products have valid data
            with conn.cursor() as cur:
                cur.execute("SELECT global_id, ifc_class, content_hash FROM ifc_products LIMIT 1")
                row = cur.fetchone()
            assert row is not None
            assert len(row[0]) == 22  # global_id
            assert row[1].startswith("Ifc")  # ifc_class
            assert len(row[2]) == 64  # content_hash (SHA-256)
        finally:
            put_conn(conn)
    
    def test_ingest_ifc_invalid_path(self, db_pool, age_graph):
        """Test that invalid IFC path raises error."""
        with pytest.raises(Exception):
            ingest_ifc("/nonexistent/file.ifc")
    
    def test_ingest_ifc_with_label(self, db_pool, age_graph, test_ifc_file):
        """Test that label is stored correctly."""
        from src.db import get_conn, put_conn
        
        label = "My custom label"
        result = ingest_ifc(str(test_ifc_file), label=label)
        
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT label FROM revisions WHERE id = %s", (result.revision_id,))
                row = cur.fetchone()
            
            assert row is not None
            assert row[0] == label
        finally:
            put_conn(conn)


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_ingest_empty_product_list(self, db_pool):
        """Test handling empty records list in insert."""
        from src.db import get_conn, put_conn
        
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                rev_id = _create_revision(cur, "empty.ifc", None)
                conn.commit()
            
            # Should handle empty list gracefully
            with conn.cursor() as cur:
                _insert_product_rows(cur, [], rev_id)
                conn.commit()
            
            # Verify no products were inserted
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM ifc_products")
                count = cur.fetchone()[0]
            assert count == 0
        finally:
            put_conn(conn)
    
    def test_close_empty_product_list(self, db_pool):
        """Test handling empty list in close."""
        from src.db import get_conn, put_conn
        
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                rev_id = _create_revision(cur, "test.ifc", None)
                conn.commit()
            
            # Should handle empty list gracefully
            with conn.cursor() as cur:
                _close_product_rows(cur, [], rev_id)
                conn.commit()
        finally:
            put_conn(conn)
