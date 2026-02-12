"""Unit tests for database module.

Tests the db.py module which provides connection pool and query helpers.
"""

import pytest

from src import db


class TestConnectionPool:
    """Test connection pool lifecycle."""
    
    def test_init_pool(self, db_pool):
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
    
    def test_get_cursor_auto_commit(self, db_pool, test_branch):
        """Test that cursor auto-commits on success."""
        branch_id = test_branch
        # Insert data
        with db.get_cursor() as cur:
            cur.execute(
                "INSERT INTO revisions (branch_id, ifc_filename) VALUES (%s, %s) RETURNING id",
                (branch_id, "test.ifc"),
            )
            rev_id = cur.fetchone()[0]
        
        # Verify data was committed
        with db.get_cursor() as cur:
            cur.execute("SELECT ifc_filename FROM revisions WHERE id = %s", (rev_id,))
            result = cur.fetchone()
        
        assert result == ("test.ifc",)
    
    def test_get_cursor_auto_rollback_on_error(self, db_pool, test_branch):
        """Test that cursor auto-rolls back on error."""
        branch_id = test_branch
        try:
            with db.get_cursor() as cur:
                cur.execute(
                    "INSERT INTO revisions (branch_id, ifc_filename) VALUES (%s, %s)",
                    (branch_id, "test.ifc"),
                )
                # Cause an error
                cur.execute("SELECT * FROM nonexistent_table")
        except Exception:
            pass  # Expected to fail
        
        # Verify data was NOT committed
        with db.get_cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM revisions")
            count = cur.fetchone()[0]
        
        assert count == 0


class TestProjectHelpers:
    """Test project and branch helper functions."""

    def test_create_project(self, db_pool):
        """Test creating a project with default branch."""
        project = db.create_project("My Project", "A description")

        assert project["id"] is not None
        assert project["name"] == "My Project"
        assert project["description"] == "A description"

        # Should have auto-created a 'main' branch
        branches = db.fetch_branches(project["id"])
        assert len(branches) == 1
        assert branches[0]["name"] == "main"

    def test_fetch_projects(self, db_pool):
        """Test fetching all projects."""
        db.create_project("Project A")
        db.create_project("Project B")

        projects = db.fetch_projects()
        assert len(projects) == 2

    def test_fetch_project(self, db_pool):
        """Test fetching a single project."""
        created = db.create_project("Find Me")
        project = db.fetch_project(created["id"])

        assert project is not None
        assert project["name"] == "Find Me"

    def test_create_branch(self, db_pool):
        """Test creating an additional branch."""
        project = db.create_project("Branch Test")
        branch = db.create_branch(project["id"], "feature-x")

        assert branch["name"] == "feature-x"
        assert branch["project_id"] == project["id"]

        branches = db.fetch_branches(project["id"])
        assert len(branches) == 2  # main + feature-x


class TestRevisionHelpers:
    """Test revision helper functions."""
    
    def test_get_latest_revision_id_empty(self, db_pool, test_branch):
        """Test getting latest revision ID when database is empty."""
        rev_id = db.get_latest_revision_id(test_branch)
        
        assert rev_id is None
    
    def test_get_latest_revision_id_with_data(self, db_pool, test_branch):
        """Test getting latest revision ID with data."""
        branch_id = test_branch
        # Insert revisions
        with db.get_cursor() as cur:
            cur.execute(
                "INSERT INTO revisions (branch_id, ifc_filename) VALUES (%s, 'v1.ifc'), (%s, 'v2.ifc')",
                (branch_id, branch_id),
            )
        
        rev_id = db.get_latest_revision_id(branch_id)
        
        assert rev_id == 2
    
    def test_fetch_revisions_empty(self, db_pool, test_branch):
        """Test fetching revisions when database is empty."""
        revisions = db.fetch_revisions(test_branch)
        
        assert isinstance(revisions, list)
        assert len(revisions) == 0
    
    def test_fetch_revisions_with_data(self, db_pool, test_branch):
        """Test fetching revisions with data."""
        branch_id = test_branch
        # Insert revisions
        with db.get_cursor() as cur:
            cur.execute(
                "INSERT INTO revisions (branch_id, label, ifc_filename) VALUES "
                "(%s, 'Rev 1', 'v1.ifc'), (%s, 'Rev 2', 'v2.ifc')",
                (branch_id, branch_id),
            )
        
        revisions = db.fetch_revisions(branch_id)
        
        assert len(revisions) == 2
        assert revisions[0]["label"] == "Rev 1"
        assert revisions[1]["label"] == "Rev 2"
    
    def test_fetch_revisions_ordered(self, db_pool, test_branch):
        """Test that revisions are ordered by id ascending."""
        branch_id = test_branch
        # Insert revisions
        with db.get_cursor() as cur:
            cur.execute(
                "INSERT INTO revisions (branch_id, ifc_filename) VALUES "
                "(%s, 'v3.ifc'), (%s, 'v1.ifc'), (%s, 'v2.ifc')",
                (branch_id, branch_id, branch_id),
            )
        
        revisions = db.fetch_revisions(branch_id)
        
        # Should be ordered by id, not filename
        assert revisions[0]["id"] < revisions[1]["id"] < revisions[2]["id"]


class TestProductQueries:
    """Test product query functions."""
    
    @pytest.fixture
    def sample_products(self, db_pool, test_branch):
        """Create sample products for testing. Returns (rev_id, branch_id)."""
        branch_id = test_branch
        with db.get_cursor() as cur:
            # Create revision
            cur.execute(
                "INSERT INTO revisions (branch_id, ifc_filename) VALUES (%s, 'test.ifc') RETURNING id",
                (branch_id,),
            )
            rev_id = cur.fetchone()[0]
            
            # Insert products
            cur.execute(
                """
                INSERT INTO ifc_products 
                (branch_id, global_id, ifc_class, name, content_hash, valid_from_rev)
                VALUES
                (%s, '0000000000000000000001', 'IfcWall', 'Wall-1', 'hash1', %s),
                (%s, '0000000000000000000002', 'IfcSlab', 'Slab-1', 'hash2', %s),
                (%s, '0000000000000000000003', 'IfcWall', 'Wall-2', 'hash3', %s)
                """,
                (branch_id, rev_id, branch_id, rev_id, branch_id, rev_id),
            )
        
        return rev_id, branch_id
    
    def test_fetch_product_at_revision(self, sample_products):
        """Test fetching single product at revision."""
        rev_id, branch_id = sample_products
        product = db.fetch_product_at_revision("0000000000000000000001", rev_id, branch_id)
        
        assert product is not None
        assert product["global_id"] == "0000000000000000000001"
        assert product["ifc_class"] == "IfcWall"
        assert product["name"] == "Wall-1"
    
    def test_fetch_product_at_revision_not_found(self, sample_products):
        """Test fetching non-existent product."""
        rev_id, branch_id = sample_products
        product = db.fetch_product_at_revision("9999999999999999999999", rev_id, branch_id)
        
        assert product is None
    
    def test_fetch_products_at_revision_all(self, sample_products):
        """Test fetching all products at revision."""
        rev_id, branch_id = sample_products
        products = db.fetch_products_at_revision(rev_id, branch_id)
        
        assert len(products) == 3
        
        # Should have all products
        global_ids = {p["global_id"] for p in products}
        assert "0000000000000000000001" in global_ids
        assert "0000000000000000000002" in global_ids
        assert "0000000000000000000003" in global_ids
    
    def test_fetch_products_at_revision_filter_by_class(self, sample_products):
        """Test fetching products filtered by IFC class."""
        rev_id, branch_id = sample_products
        products = db.fetch_products_at_revision(rev_id, branch_id, ifc_class="IfcWall")
        
        assert len(products) == 2
        
        # Should only have walls
        for p in products:
            assert p["ifc_class"] == "IfcWall"
    
    def test_fetch_products_at_revision_filter_by_container(self, db_pool, test_branch):
        """Test fetching products filtered by container."""
        branch_id = test_branch
        with db.get_cursor() as cur:
            # Create revision
            cur.execute(
                "INSERT INTO revisions (branch_id, ifc_filename) VALUES (%s, 'test.ifc') RETURNING id",
                (branch_id,),
            )
            rev_id = cur.fetchone()[0]
            
            # Insert products with containers
            cur.execute(
                """
                INSERT INTO ifc_products 
                (branch_id, global_id, ifc_class, name, contained_in, content_hash, valid_from_rev)
                VALUES
                (%s, '0000000000000000000001', 'IfcBuildingStorey', 'Level-1', NULL, 'hash1', %s),
                (%s, '0000000000000000000002', 'IfcWall', 'Wall-1', '0000000000000000000001', 'hash2', %s),
                (%s, '0000000000000000000003', 'IfcWall', 'Wall-2', '0000000000000000000001', 'hash3', %s)
                """,
                (branch_id, rev_id, branch_id, rev_id, branch_id, rev_id),
            )
        
        # Fetch products in container
        products = db.fetch_products_at_revision(
            rev_id, branch_id, contained_in="0000000000000000000001"
        )
        
        assert len(products) == 2
        for p in products:
            assert p["contained_in"] == "0000000000000000000001"
    
    def test_fetch_spatial_container(self, db_pool, test_branch):
        """Test fetching spatial container for element."""
        branch_id = test_branch
        with db.get_cursor() as cur:
            # Create revision
            cur.execute(
                "INSERT INTO revisions (branch_id, ifc_filename) VALUES (%s, 'test.ifc') RETURNING id",
                (branch_id,),
            )
            rev_id = cur.fetchone()[0]
            
            # Insert container and element
            cur.execute(
                """
                INSERT INTO ifc_products 
                (branch_id, global_id, ifc_class, name, content_hash, valid_from_rev)
                VALUES
                (%s, '0000000000000000000001', 'IfcBuildingStorey', 'Level-1', 'hash1', %s)
                """,
                (branch_id, rev_id),
            )
        
        container = db.fetch_spatial_container("0000000000000000000001", rev_id, branch_id)
        
        assert container is not None
        assert container["global_id"] == "0000000000000000000001"
    
    def test_fetch_spatial_container_none(self, sample_products):
        """Test fetching container when none exists."""
        rev_id, branch_id = sample_products
        container = db.fetch_spatial_container(None, rev_id, branch_id)
        
        assert container is None


class TestSCDType2Queries:
    """Test SCD Type 2 time-travel queries."""
    
    def test_scd_type_2_current_products(self, db_pool, test_branch):
        """Test querying current (non-closed) products."""
        branch_id = test_branch
        with db.get_cursor() as cur:
            # Create two revisions
            cur.execute(
                "INSERT INTO revisions (branch_id, ifc_filename) VALUES (%s, 'v1.ifc') RETURNING id",
                (branch_id,),
            )
            rev1 = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO revisions (branch_id, ifc_filename) VALUES (%s, 'v2.ifc') RETURNING id",
                (branch_id,),
            )
            rev2 = cur.fetchone()[0]
            
            # Insert product in rev1
            cur.execute(
                """
                INSERT INTO ifc_products 
                (branch_id, global_id, ifc_class, name, content_hash, valid_from_rev, valid_to_rev)
                VALUES
                (%s, '0000000000000000000001', 'IfcWall', 'Wall-1', 'hash1', %s, %s)
                """,
                (branch_id, rev1, rev2),
            )
            
            # Insert updated version in rev2 (current)
            cur.execute(
                """
                INSERT INTO ifc_products 
                (branch_id, global_id, ifc_class, name, content_hash, valid_from_rev)
                VALUES
                (%s, '0000000000000000000001', 'IfcWall', 'Wall-1-Updated', 'hash2', %s)
                """,
                (branch_id, rev2),
            )
        
        # Fetch at rev2 should get updated version
        product = db.fetch_product_at_revision("0000000000000000000001", rev2, branch_id)
        
        assert product is not None
        assert product["name"] == "Wall-1-Updated"
    
    def test_scd_type_2_historical_query(self, db_pool, test_branch):
        """Test querying historical state."""
        branch_id = test_branch
        with db.get_cursor() as cur:
            # Create two revisions
            cur.execute(
                "INSERT INTO revisions (branch_id, ifc_filename) VALUES (%s, 'v1.ifc') RETURNING id",
                (branch_id,),
            )
            rev1 = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO revisions (branch_id, ifc_filename) VALUES (%s, 'v2.ifc') RETURNING id",
                (branch_id,),
            )
            rev2 = cur.fetchone()[0]
            
            # Insert product in rev1
            cur.execute(
                """
                INSERT INTO ifc_products 
                (branch_id, global_id, ifc_class, name, content_hash, valid_from_rev, valid_to_rev)
                VALUES
                (%s, '0000000000000000000001', 'IfcWall', 'Wall-1', 'hash1', %s, %s)
                """,
                (branch_id, rev1, rev2),
            )
            
            # Insert updated version in rev2
            cur.execute(
                """
                INSERT INTO ifc_products 
                (branch_id, global_id, ifc_class, name, content_hash, valid_from_rev)
                VALUES
                (%s, '0000000000000000000001', 'IfcWall', 'Wall-1-Updated', 'hash2', %s)
                """,
                (branch_id, rev2),
            )
        
        # Fetch at rev1 should get original version
        product = db.fetch_product_at_revision("0000000000000000000001", rev1, branch_id)
        
        assert product is not None
        assert product["name"] == "Wall-1"


class TestRevisionDiff:
    """Test revision diff functionality."""
    
    def test_fetch_revision_diff_empty(self, db_pool, test_branch):
        """Test diff between two empty states."""
        branch_id = test_branch
        with db.get_cursor() as cur:
            cur.execute(
                "INSERT INTO revisions (branch_id, ifc_filename) VALUES (%s, 'v1.ifc'), (%s, 'v2.ifc')",
                (branch_id, branch_id),
            )
        
        diff = db.fetch_revision_diff(1, 2, branch_id)
        
        assert diff["added"] == []
        assert diff["modified"] == []
        assert diff["deleted"] == []
    
    def test_fetch_revision_diff_added(self, db_pool, test_branch):
        """Test detecting added products."""
        branch_id = test_branch
        with db.get_cursor() as cur:
            # Create revisions
            cur.execute(
                "INSERT INTO revisions (branch_id, ifc_filename) VALUES (%s, 'v1.ifc') RETURNING id",
                (branch_id,),
            )
            rev1 = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO revisions (branch_id, ifc_filename) VALUES (%s, 'v2.ifc') RETURNING id",
                (branch_id,),
            )
            rev2 = cur.fetchone()[0]
            
            # Add product in rev2
            cur.execute(
                """
                INSERT INTO ifc_products 
                (branch_id, global_id, ifc_class, name, content_hash, valid_from_rev)
                VALUES
                (%s, '0000000000000000000001', 'IfcWall', 'Wall-1', 'hash1', %s)
                """,
                (branch_id, rev2),
            )
        
        diff = db.fetch_revision_diff(rev1, rev2, branch_id)
        
        assert len(diff["added"]) == 1
        assert diff["added"][0]["global_id"] == "0000000000000000000001"
        assert len(diff["modified"]) == 0
        assert len(diff["deleted"]) == 0
    
    def test_fetch_revision_diff_deleted(self, db_pool, test_branch):
        """Test detecting deleted products."""
        branch_id = test_branch
        with db.get_cursor() as cur:
            # Create revisions
            cur.execute(
                "INSERT INTO revisions (branch_id, ifc_filename) VALUES (%s, 'v1.ifc') RETURNING id",
                (branch_id,),
            )
            rev1 = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO revisions (branch_id, ifc_filename) VALUES (%s, 'v2.ifc') RETURNING id",
                (branch_id,),
            )
            rev2 = cur.fetchone()[0]
            
            # Add product in rev1, delete in rev2
            cur.execute(
                """
                INSERT INTO ifc_products 
                (branch_id, global_id, ifc_class, name, content_hash, valid_from_rev, valid_to_rev)
                VALUES
                (%s, '0000000000000000000001', 'IfcWall', 'Wall-1', 'hash1', %s, %s)
                """,
                (branch_id, rev1, rev2),
            )
        
        diff = db.fetch_revision_diff(rev1, rev2, branch_id)
        
        assert len(diff["added"]) == 0
        assert len(diff["modified"]) == 0
        assert len(diff["deleted"]) == 1
        assert diff["deleted"][0]["global_id"] == "0000000000000000000001"
    
    def test_fetch_revision_diff_modified(self, db_pool, test_branch):
        """Test detecting modified products."""
        branch_id = test_branch
        with db.get_cursor() as cur:
            # Create revisions
            cur.execute(
                "INSERT INTO revisions (branch_id, ifc_filename) VALUES (%s, 'v1.ifc') RETURNING id",
                (branch_id,),
            )
            rev1 = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO revisions (branch_id, ifc_filename) VALUES (%s, 'v2.ifc') RETURNING id",
                (branch_id,),
            )
            rev2 = cur.fetchone()[0]
            
            # Original version in rev1
            cur.execute(
                """
                INSERT INTO ifc_products 
                (branch_id, global_id, ifc_class, name, content_hash, valid_from_rev, valid_to_rev)
                VALUES
                (%s, '0000000000000000000001', 'IfcWall', 'Wall-1', 'hash1', %s, %s)
                """,
                (branch_id, rev1, rev2),
            )
            
            # Modified version in rev2 (different hash)
            cur.execute(
                """
                INSERT INTO ifc_products 
                (branch_id, global_id, ifc_class, name, content_hash, valid_from_rev)
                VALUES
                (%s, '0000000000000000000001', 'IfcWall', 'Wall-1-Modified', 'hash2', %s)
                """,
                (branch_id, rev2),
            )
        
        diff = db.fetch_revision_diff(rev1, rev2, branch_id)
        
        assert len(diff["added"]) == 0
        assert len(diff["modified"]) == 1
        assert diff["modified"][0]["global_id"] == "0000000000000000000001"
        assert len(diff["deleted"]) == 0
