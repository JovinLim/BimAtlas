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
from src.services.ifc.geometry import IfcEntityRecord


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
            # From endpoint is always a rooted IFC entity (22-char GlobalId).
            assert len(rel.from_global_id) == 22
            # To endpoint may be a rooted entity or a synthetic shape rep id.
            assert len(rel.to_global_id) >= 22
    
    def test_extract_relationships_types(self, test_ifc_file):
        """Test that we extract expected relationship types."""
        import ifcopenshell
        model = ifcopenshell.open(str(test_ifc_file))
        
        relationships = _extract_relationships(model)
        
        rel_types = {r.relationship_type for r in relationships}

        # Should have core spatial relationships
        assert "IfcRelAggregates" in rel_types or "IfcRelContainedInSpatialStructure" in rel_types

        # Synthetic shape representation edges should always be present when geometry exists.
        assert "HasShapeRepresentation" in rel_types


class TestDiffEngine:
    """Test product diffing logic."""
    
    def test_diff_products_all_added(self):
        """Test diff when all products are new."""
        new_records = [
            IfcEntityRecord(
                ifc_global_id="0000000000000000000001",
                ifc_class="IfcWall",
                attributes={"Name": "Wall-1"},
                geometry=None,
                content_hash="hash1",
            ),
            IfcEntityRecord(
                ifc_global_id="0000000000000000000002",
                ifc_class="IfcSlab",
                attributes={"Name": "Slab-1"},
                geometry=None,
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
        
        assert added[0].ifc_global_id in ["0000000000000000000001", "0000000000000000000002"]
    
    def test_diff_products_all_unchanged(self):
        """Test diff when all products are unchanged."""
        new_records = [
            IfcEntityRecord(
                ifc_global_id="0000000000000000000001",
                ifc_class="IfcWall",
                attributes={"Name": "Wall-1"},
                geometry=None,
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
            IfcEntityRecord(
                ifc_global_id="0000000000000000000001",
                ifc_class="IfcWall",
                attributes={"Name": "Wall-1-Updated"},
                geometry=None,
                content_hash="hash1_new",
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
        assert modified[0].ifc_global_id == "0000000000000000000001"
    
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
            IfcEntityRecord(ifc_global_id="0000000000000000000001", ifc_class="IfcWall", attributes={"Name": "Wall-1"}, geometry=None, content_hash="hash1"),
            IfcEntityRecord(ifc_global_id="0000000000000000000002", ifc_class="IfcSlab", attributes={"Name": "Slab-1-Updated"}, geometry=None, content_hash="hash2_new"),
            IfcEntityRecord(ifc_global_id="0000000000000000000004", ifc_class="IfcDoor", attributes={"Name": "Door-1"}, geometry=None, content_hash="hash4"),
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
        
        assert added[0].ifc_global_id == "0000000000000000000004"
        assert modified[0].ifc_global_id == "0000000000000000000002"
        assert "0000000000000000000003" in deleted_gids
        assert "0000000000000000000001" in unchanged_gids


class TestDatabaseOperations:
    """Test database operations during ingestion."""
    
    def test_create_revision(self, db_pool, test_branch):
        """Test creating a new revision."""
        from src.db import get_conn, put_conn
        
        branch_id = test_branch
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                rev_id, rev_seq = _create_revision(cur, branch_id, "test.ifc", "Test revision")  # type: ignore[misc]
                conn.commit()
            
            # Verify revision was created
            with conn.cursor() as cur:
                cur.execute("SELECT revision_id, branch_id, commit_message, ifc_filename, revision_seq FROM revision WHERE revision_id = %s", (rev_id,))
                row = cur.fetchone()
            
            assert row is not None
            assert row[0] == rev_id
            assert str(row[1]) == str(branch_id)
            assert row[2] == "Test revision"
            assert row[3] == "test.ifc"
            assert int(row[4]) == int(rev_seq)
        finally:
            put_conn(conn)
    
    def test_load_current_hashes_empty(self, db_pool, test_branch):
        """Test loading hashes when database is empty."""
        from src.db import get_conn, put_conn
        
        branch_id = test_branch
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                hashes = _load_current_hashes(cur, branch_id)
            
            assert isinstance(hashes, dict)
            assert len(hashes) == 0
        finally:
            put_conn(conn)
    
    def test_insert_product_rows(self, db_pool, test_branch):
        """Test inserting product rows."""
        from src.db import get_conn, put_conn
        
        branch_id = test_branch
        conn = get_conn()
        try:
            # Create revision first
            with conn.cursor() as cur:
                rev_id, _ = _create_revision(cur, branch_id, "test.ifc", None)  # type: ignore[misc]
                conn.commit()
            
            # Insert entities (rev_id from _create_revision is revision_id UUID)
            records = [
                IfcEntityRecord(
                    ifc_global_id="0000000000000000000001",
                    ifc_class="IfcWall",
                    attributes={"Name": "Wall-1"},
                    geometry=None,
                    content_hash="hash1",
                ),
            ]
            
            with conn.cursor() as cur:
                _insert_product_rows(cur, records, rev_id, branch_id)
                conn.commit()
            
            # Verify products were inserted
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM ifc_entity WHERE created_in_revision_id = %s", (rev_id,))
                count = cur.fetchone()[0]
            
            assert count == 1
        finally:
            put_conn(conn)
    
    def test_close_product_rows(self, db_pool, test_branch):
        """Test closing product rows (SCD Type 2)."""
        from src.db import get_conn, put_conn
        
        branch_id = test_branch
        conn = get_conn()
        try:
            # Create first revision and insert product
            with conn.cursor() as cur:
                rev_id_1, _ = _create_revision(cur, branch_id, "test_v1.ifc", None)  # type: ignore[misc]
                conn.commit()
            
            records = [
                IfcEntityRecord(
                    ifc_global_id="0000000000000000000001",
                    ifc_class="IfcWall",
                    attributes={"Name": "Wall-1"},
                    geometry=None,
                    content_hash="hash1",
                ),
            ]
            
            with conn.cursor() as cur:
                _insert_product_rows(cur, records, rev_id_1, branch_id)
                conn.commit()
            
            # Create second revision and close the product
            with conn.cursor() as cur:
                rev_id_2, _ = _create_revision(cur, branch_id, "test_v2.ifc", None)  # type: ignore[misc]
                conn.commit()
            
            with conn.cursor() as cur:
                _close_product_rows(cur, ["0000000000000000000001"], rev_id_2, branch_id)
                conn.commit()
            
            # Verify product was closed
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT obsoleted_in_revision_id FROM ifc_entity WHERE ifc_global_id = %s AND branch_id = %s",
                    ("0000000000000000000001", branch_id)
                )
                row = cur.fetchone()
            
            assert row is not None
            assert str(row[0]) == str(rev_id_2)
        finally:
            put_conn(conn)


class TestFullIngestion:
    """Test full ingestion pipeline."""
    
    def test_ingest_ifc_first_import(self, db_pool, age_graph, test_ifc_file, test_branch):
        """Test ingesting IFC file for the first time."""
        branch_id = test_branch
        result = ingest_ifc(str(test_ifc_file), branch_id=branch_id, label="Initial import")
        
        assert isinstance(result, IngestionResult)
        assert result.revision_id is not None and isinstance(result.revision_id, str)
        assert result.branch_id == branch_id
        assert result.total_products > 0
        assert result.added == result.total_products  # All products are added
        assert result.modified == 0
        assert result.deleted == 0
        assert result.unchanged == 0
        assert result.edges_created >= 0
    
    def test_ingest_ifc_second_import_unchanged(self, db_pool, age_graph, test_ifc_file, test_branch):
        """Test importing same IFC file twice (all unchanged)."""
        branch_id = test_branch
        # First import
        result1 = ingest_ifc(str(test_ifc_file), branch_id=branch_id, label="Import 1")
        
        # Second import (same file)
        result2 = ingest_ifc(str(test_ifc_file), branch_id=branch_id, label="Import 2")
        
        assert result2.revision_id != result1.revision_id
        assert result2.total_products == result1.total_products
        assert result2.added == 0
        assert result2.modified == 0
        assert result2.deleted == 0
        assert result2.unchanged == result1.total_products
    
    def test_ingest_ifc_creates_database_records(self, db_pool, age_graph, test_ifc_file, test_branch):
        """Test that ingestion creates correct database records."""
        from src.db import get_conn, put_conn
        
        branch_id = test_branch
        result = ingest_ifc(str(test_ifc_file), branch_id=branch_id, label="Test import")
        
        conn = get_conn()
        try:
            # Check revision was created
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM revision WHERE branch_id = %s", (branch_id,))
                rev_count = cur.fetchone()[0]
            assert rev_count == 1
            
            # Check products were inserted
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM ifc_entity WHERE branch_id = %s AND obsoleted_in_revision_id IS NULL",
                    (branch_id,),
                )
                product_count = cur.fetchone()[0]
            assert product_count == result.total_products
            
            # Check products have valid data
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT ifc_global_id, ifc_class, content_hash FROM ifc_entity WHERE branch_id = %s LIMIT 1",
                    (branch_id,),
                )
                row = cur.fetchone()
            assert row is not None
            # Rooted IFC entities have 22-char GlobalIds; synthetic entities (shape reps)
            # use longer ids that still start with the owning product's GlobalId.
            assert len(row[0]) >= 22  # ifc_global_id
            assert row[1].startswith("Ifc")  # ifc_class
            assert len(row[2]) == 64  # content_hash (SHA-256)
        finally:
            put_conn(conn)
    
    def test_ingest_ifc_invalid_path(self, db_pool, age_graph, test_branch):
        """Test that invalid IFC path raises error."""
        with pytest.raises(Exception):
            ingest_ifc("/nonexistent/file.ifc", branch_id=test_branch)
    
    def test_ingest_ifc_with_label(self, db_pool, age_graph, test_ifc_file, test_branch):
        """Test that label is stored correctly."""
        from src.db import get_conn, put_conn
        
        branch_id = test_branch
        label = "My custom label"
        result = ingest_ifc(str(test_ifc_file), branch_id=branch_id, label=label)
        
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT commit_message FROM revision WHERE revision_id = %s", (result.revision_id,))
                row = cur.fetchone()
            
            assert row is not None
            assert row[0] == label
        finally:
            put_conn(conn)

    def test_ingest_ifc_reports_progress(self, db_pool, age_graph, test_ifc_file, test_branch):
        """Progress callback should receive ordered ingestion milestones."""
        events: list[dict] = []

        result = ingest_ifc(
            str(test_ifc_file),
            branch_id=test_branch,
            label="Progress import",
            progress_callback=events.append,
        )

        assert result.total_products > 0
        assert events, "expected progress events during ingestion"
        assert events[0]["progress"] == 5
        assert events[-1]["progress"] == 100
        assert events[-1]["stage"] == "complete"


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_ingest_empty_product_list(self, db_pool, test_branch):
        """Test handling empty records list in insert."""
        from src.db import get_conn, put_conn
        
        branch_id = test_branch
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                rev_id, _ = _create_revision(cur, branch_id, "empty.ifc", None)  # type: ignore[misc]
                conn.commit()
            
            # Should handle empty list gracefully
            with conn.cursor() as cur:
                _insert_product_rows(cur, [], rev_id, branch_id)
                conn.commit()
            
            # Verify no products were inserted
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM ifc_entity")
                count = cur.fetchone()[0]
            assert count == 0
        finally:
            put_conn(conn)
    
    def test_close_empty_product_list(self, db_pool, test_branch):
        """Test handling empty list in close."""
        from src.db import get_conn, put_conn
        
        branch_id = test_branch
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                rev_id, _ = _create_revision(cur, branch_id, "test.ifc", None)  # type: ignore[misc]
                conn.commit()
            
            # Should handle empty list gracefully
            with conn.cursor() as cur:
                _close_product_rows(cur, [], rev_id, branch_id)
                conn.commit()
        finally:
            put_conn(conn)
