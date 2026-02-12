"""Unit tests for database module.

Tests the db.py module which provides connection pool and query helpers.
"""

import pytest

from src import db


class TestConnectionPool:
    """Test connection pool lifecycle."""
    
    def test_init_pool(self):
        """Test initializing connection pool."""
        # Pool should be initialized by fixture, test it works
        assert db._pool is not None
    
    def test_get_conn_returns_connection(self, db_pool):
        """Test getting connection from pool."""
        conn = db.get_conn()
        
        assert conn is not None
        assert not conn.closed
        
        # Test connection works
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            result = cur.fetchone()
        
        assert result == (1,)
        
        db.put_conn(conn)
    
    def test_get_conn_sets_search_path(self, db_pool):
        """Test that get_conn sets AGE search path."""
        conn = db.get_conn()
        
        try:
            with conn.cursor() as cur:
                cur.execute("SHOW search_path")
                search_path = cur.fetchone()[0]
            
            # Should include ag_catalog
            assert "ag_catalog" in search_path
        finally:
            db.put_conn(conn)
    
    def test_put_conn_returns_connection(self, db_pool):
        """Test returning connection to pool."""
        conn = db.get_conn()
        db.put_conn(conn)
        
        # Should be able to get another connection
        conn2 = db.get_conn()
        assert conn2 is not None
        db.put_conn(conn2)
    
    def test_multiple_connections(self, db_pool):
        """Test getting multiple connections from pool."""
        conn1 = db.get_conn()
        conn2 = db.get_conn()
        
        assert conn1 is not None
        assert conn2 is not None
        assert conn1 != conn2  # Should be different connections
        
        db.put_conn(conn1)
        db.put_conn(conn2)


class TestCursorContextManager:
    """Test cursor context manager."""
    
    def test_get_cursor_basic(self, db_pool):
        """Test basic cursor usage."""
        with db.get_cursor() as cur:
            cur.execute("SELECT 1 as test")
            result = cur.fetchone()
        
        assert result == (1,)
    
    def test_get_cursor_dict_mode(self, db_pool):
        """Test cursor with dict_cursor=True."""
        with db.get_cursor(dict_cursor=True) as cur:
            cur.execute("SELECT 1 as test")
            result = cur.fetchone()
        
        assert isinstance(result, dict)
        assert result["test"] == 1
    
    def test_get_cursor_auto_commit(self, db_pool, clean_db):
        """Test that cursor auto-commits on success."""
        # Insert data
        with db.get_cursor() as cur:
            cur.execute(
                "INSERT INTO revisions (ifc_filename) VALUES (%s) RETURNING id",
                ("test.ifc",),
            )
            rev_id = cur.fetchone()[0]
        
        # Verify data was committed
        with db.get_cursor() as cur:
            cur.execute("SELECT ifc_filename FROM revisions WHERE id = %s", (rev_id,))
            result = cur.fetchone()
        
        assert result == ("test.ifc",)
    
    def test_get_cursor_auto_rollback_on_error(self, db_pool, clean_db):
        """Test that cursor auto-rolls back on error."""
        try:
            with db.get_cursor() as cur:
                cur.execute("INSERT INTO revisions (ifc_filename) VALUES (%s)", ("test.ifc",))
                # Cause an error
                cur.execute("SELECT * FROM nonexistent_table")
        except Exception:
            pass  # Expected to fail
        
        # Verify data was NOT committed
        with db.get_cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM revisions")
            count = cur.fetchone()[0]
        
        assert count == 0


class TestRevisionHelpers:
    """Test revision helper functions."""
    
    def test_get_latest_revision_id_empty(self, db_pool, clean_db):
        """Test getting latest revision ID when database is empty."""
        rev_id = db.get_latest_revision_id()
        
        assert rev_id is None
    
    def test_get_latest_revision_id_with_data(self, db_pool, clean_db):
        """Test getting latest revision ID with data."""
        # Insert revisions
        with db.get_cursor() as cur:
            cur.execute("INSERT INTO revisions (ifc_filename) VALUES ('v1.ifc'), ('v2.ifc')")
        
        rev_id = db.get_latest_revision_id()
        
        assert rev_id == 2
    
    def test_fetch_revisions_empty(self, db_pool, clean_db):
        """Test fetching revisions when database is empty."""
        revisions = db.fetch_revisions()
        
        assert isinstance(revisions, list)
        assert len(revisions) == 0
    
    def test_fetch_revisions_with_data(self, db_pool, clean_db):
        """Test fetching revisions with data."""
        # Insert revisions
        with db.get_cursor() as cur:
            cur.execute(
                "INSERT INTO revisions (label, ifc_filename) VALUES "
                "('Rev 1', 'v1.ifc'), ('Rev 2', 'v2.ifc')"
            )
        
        revisions = db.fetch_revisions()
        
        assert len(revisions) == 2
        assert revisions[0]["id"] == 1
        assert revisions[0]["label"] == "Rev 1"
        assert revisions[1]["id"] == 2
        assert revisions[1]["label"] == "Rev 2"
    
    def test_fetch_revisions_ordered(self, db_pool, clean_db):
        """Test that revisions are ordered by id ascending."""
        # Insert revisions
        with db.get_cursor() as cur:
            cur.execute(
                "INSERT INTO revisions (ifc_filename) VALUES ('v3.ifc'), ('v1.ifc'), ('v2.ifc')"
            )
        
        revisions = db.fetch_revisions()
        
        # Should be ordered by id, not filename
        assert revisions[0]["id"] == 1
        assert revisions[1]["id"] == 2
        assert revisions[2]["id"] == 3


class TestProductQueries:
    """Test product query functions."""
    
    @pytest.fixture
    def sample_products(self, db_pool, clean_db):
        """Create sample products for testing."""
        with db.get_cursor() as cur:
            # Create revision
            cur.execute("INSERT INTO revisions (ifc_filename) VALUES ('test.ifc') RETURNING id")
            rev_id = cur.fetchone()[0]
            
            # Insert products
            cur.execute(
                """
                INSERT INTO ifc_products 
                (global_id, ifc_class, name, content_hash, valid_from_rev)
                VALUES
                ('0000000000000000000001', 'IfcWall', 'Wall-1', 'hash1', %s),
                ('0000000000000000000002', 'IfcSlab', 'Slab-1', 'hash2', %s),
                ('0000000000000000000003', 'IfcWall', 'Wall-2', 'hash3', %s)
                """,
                (rev_id, rev_id, rev_id),
            )
        
        return rev_id
    
    def test_fetch_product_at_revision(self, sample_products):
        """Test fetching single product at revision."""
        product = db.fetch_product_at_revision("0000000000000000000001", sample_products)
        
        assert product is not None
        assert product["global_id"] == "0000000000000000000001"
        assert product["ifc_class"] == "IfcWall"
        assert product["name"] == "Wall-1"
    
    def test_fetch_product_at_revision_not_found(self, sample_products):
        """Test fetching non-existent product."""
        product = db.fetch_product_at_revision("9999999999999999999999", sample_products)
        
        assert product is None
    
    def test_fetch_products_at_revision_all(self, sample_products):
        """Test fetching all products at revision."""
        products = db.fetch_products_at_revision(sample_products)
        
        assert len(products) == 3
        
        # Should have all products
        global_ids = {p["global_id"] for p in products}
        assert "0000000000000000000001" in global_ids
        assert "0000000000000000000002" in global_ids
        assert "0000000000000000000003" in global_ids
    
    def test_fetch_products_at_revision_filter_by_class(self, sample_products):
        """Test fetching products filtered by IFC class."""
        products = db.fetch_products_at_revision(sample_products, ifc_class="IfcWall")
        
        assert len(products) == 2
        
        # Should only have walls
        for p in products:
            assert p["ifc_class"] == "IfcWall"
    
    def test_fetch_products_at_revision_filter_by_container(self, db_pool, clean_db):
        """Test fetching products filtered by container."""
        with db.get_cursor() as cur:
            # Create revision
            cur.execute("INSERT INTO revisions (ifc_filename) VALUES ('test.ifc') RETURNING id")
            rev_id = cur.fetchone()[0]
            
            # Insert products with containers
            cur.execute(
                """
                INSERT INTO ifc_products 
                (global_id, ifc_class, name, contained_in, content_hash, valid_from_rev)
                VALUES
                ('0000000000000000000001', 'IfcBuildingStorey', 'Level-1', NULL, 'hash1', %s),
                ('0000000000000000000002', 'IfcWall', 'Wall-1', '0000000000000000000001', 'hash2', %s),
                ('0000000000000000000003', 'IfcWall', 'Wall-2', '0000000000000000000001', 'hash3', %s)
                """,
                (rev_id, rev_id, rev_id),
            )
        
        # Fetch products in container
        products = db.fetch_products_at_revision(
            rev_id, contained_in="0000000000000000000001"
        )
        
        assert len(products) == 2
        for p in products:
            assert p["contained_in"] == "0000000000000000000001"
    
    def test_fetch_spatial_container(self, db_pool, clean_db):
        """Test fetching spatial container for element."""
        with db.get_cursor() as cur:
            # Create revision
            cur.execute("INSERT INTO revisions (ifc_filename) VALUES ('test.ifc') RETURNING id")
            rev_id = cur.fetchone()[0]
            
            # Insert container and element
            cur.execute(
                """
                INSERT INTO ifc_products 
                (global_id, ifc_class, name, content_hash, valid_from_rev)
                VALUES
                ('0000000000000000000001', 'IfcBuildingStorey', 'Level-1', 'hash1', %s)
                """,
                (rev_id,),
            )
        
        container = db.fetch_spatial_container("0000000000000000000001", rev_id)
        
        assert container is not None
        assert container["global_id"] == "0000000000000000000001"
    
    def test_fetch_spatial_container_none(self, sample_products):
        """Test fetching container when none exists."""
        container = db.fetch_spatial_container(None, sample_products)
        
        assert container is None


class TestSCDType2Queries:
    """Test SCD Type 2 time-travel queries."""
    
    def test_scd_type_2_current_products(self, db_pool, clean_db):
        """Test querying current (non-closed) products."""
        with db.get_cursor() as cur:
            # Create two revisions
            cur.execute("INSERT INTO revisions (ifc_filename) VALUES ('v1.ifc') RETURNING id")
            rev1 = cur.fetchone()[0]
            cur.execute("INSERT INTO revisions (ifc_filename) VALUES ('v2.ifc') RETURNING id")
            rev2 = cur.fetchone()[0]
            
            # Insert product in rev1
            cur.execute(
                """
                INSERT INTO ifc_products 
                (global_id, ifc_class, name, content_hash, valid_from_rev, valid_to_rev)
                VALUES
                ('0000000000000000000001', 'IfcWall', 'Wall-1', 'hash1', %s, %s)
                """,
                (rev1, rev2),
            )
            
            # Insert updated version in rev2 (current)
            cur.execute(
                """
                INSERT INTO ifc_products 
                (global_id, ifc_class, name, content_hash, valid_from_rev)
                VALUES
                ('0000000000000000000001', 'IfcWall', 'Wall-1-Updated', 'hash2', %s)
                """,
                (rev2,),
            )
        
        # Fetch at rev2 should get updated version
        product = db.fetch_product_at_revision("0000000000000000000001", rev2)
        
        assert product is not None
        assert product["name"] == "Wall-1-Updated"
    
    def test_scd_type_2_historical_query(self, db_pool, clean_db):
        """Test querying historical state."""
        with db.get_cursor() as cur:
            # Create two revisions
            cur.execute("INSERT INTO revisions (ifc_filename) VALUES ('v1.ifc') RETURNING id")
            rev1 = cur.fetchone()[0]
            cur.execute("INSERT INTO revisions (ifc_filename) VALUES ('v2.ifc') RETURNING id")
            rev2 = cur.fetchone()[0]
            
            # Insert product in rev1
            cur.execute(
                """
                INSERT INTO ifc_products 
                (global_id, ifc_class, name, content_hash, valid_from_rev, valid_to_rev)
                VALUES
                ('0000000000000000000001', 'IfcWall', 'Wall-1', 'hash1', %s, %s)
                """,
                (rev1, rev2),
            )
            
            # Insert updated version in rev2
            cur.execute(
                """
                INSERT INTO ifc_products 
                (global_id, ifc_class, name, content_hash, valid_from_rev)
                VALUES
                ('0000000000000000000001', 'IfcWall', 'Wall-1-Updated', 'hash2', %s)
                """,
                (rev2,),
            )
        
        # Fetch at rev1 should get original version
        product = db.fetch_product_at_revision("0000000000000000000001", rev1)
        
        assert product is not None
        assert product["name"] == "Wall-1"


class TestRevisionDiff:
    """Test revision diff functionality."""
    
    def test_fetch_revision_diff_empty(self, db_pool, clean_db):
        """Test diff between two empty states."""
        with db.get_cursor() as cur:
            cur.execute("INSERT INTO revisions (ifc_filename) VALUES ('v1.ifc'), ('v2.ifc')")
        
        diff = db.fetch_revision_diff(1, 2)
        
        assert diff["added"] == []
        assert diff["modified"] == []
        assert diff["deleted"] == []
    
    def test_fetch_revision_diff_added(self, db_pool, clean_db):
        """Test detecting added products."""
        with db.get_cursor() as cur:
            # Create revisions
            cur.execute("INSERT INTO revisions (ifc_filename) VALUES ('v1.ifc') RETURNING id")
            rev1 = cur.fetchone()[0]
            cur.execute("INSERT INTO revisions (ifc_filename) VALUES ('v2.ifc') RETURNING id")
            rev2 = cur.fetchone()[0]
            
            # Add product in rev2
            cur.execute(
                """
                INSERT INTO ifc_products 
                (global_id, ifc_class, name, content_hash, valid_from_rev)
                VALUES
                ('0000000000000000000001', 'IfcWall', 'Wall-1', 'hash1', %s)
                """,
                (rev2,),
            )
        
        diff = db.fetch_revision_diff(rev1, rev2)
        
        assert len(diff["added"]) == 1
        assert diff["added"][0]["global_id"] == "0000000000000000000001"
        assert len(diff["modified"]) == 0
        assert len(diff["deleted"]) == 0
    
    def test_fetch_revision_diff_deleted(self, db_pool, clean_db):
        """Test detecting deleted products."""
        with db.get_cursor() as cur:
            # Create revisions
            cur.execute("INSERT INTO revisions (ifc_filename) VALUES ('v1.ifc') RETURNING id")
            rev1 = cur.fetchone()[0]
            cur.execute("INSERT INTO revisions (ifc_filename) VALUES ('v2.ifc') RETURNING id")
            rev2 = cur.fetchone()[0]
            
            # Add product in rev1, delete in rev2
            cur.execute(
                """
                INSERT INTO ifc_products 
                (global_id, ifc_class, name, content_hash, valid_from_rev, valid_to_rev)
                VALUES
                ('0000000000000000000001', 'IfcWall', 'Wall-1', 'hash1', %s, %s)
                """,
                (rev1, rev2),
            )
        
        diff = db.fetch_revision_diff(rev1, rev2)
        
        assert len(diff["added"]) == 0
        assert len(diff["modified"]) == 0
        assert len(diff["deleted"]) == 1
        assert diff["deleted"][0]["global_id"] == "0000000000000000000001"
    
    def test_fetch_revision_diff_modified(self, db_pool, clean_db):
        """Test detecting modified products."""
        with db.get_cursor() as cur:
            # Create revisions
            cur.execute("INSERT INTO revisions (ifc_filename) VALUES ('v1.ifc') RETURNING id")
            rev1 = cur.fetchone()[0]
            cur.execute("INSERT INTO revisions (ifc_filename) VALUES ('v2.ifc') RETURNING id")
            rev2 = cur.fetchone()[0]
            
            # Original version in rev1
            cur.execute(
                """
                INSERT INTO ifc_products 
                (global_id, ifc_class, name, content_hash, valid_from_rev, valid_to_rev)
                VALUES
                ('0000000000000000000001', 'IfcWall', 'Wall-1', 'hash1', %s, %s)
                """,
                (rev1, rev2),
            )
            
            # Modified version in rev2 (different hash)
            cur.execute(
                """
                INSERT INTO ifc_products 
                (global_id, ifc_class, name, content_hash, valid_from_rev)
                VALUES
                ('0000000000000000000001', 'IfcWall', 'Wall-1-Modified', 'hash2', %s)
                """,
                (rev2,),
            )
        
        diff = db.fetch_revision_diff(rev1, rev2)
        
        assert len(diff["added"]) == 0
        assert len(diff["modified"]) == 1
        assert diff["modified"][0]["global_id"] == "0000000000000000000001"
        assert len(diff["deleted"]) == 0
