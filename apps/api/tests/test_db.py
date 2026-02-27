"""Unit tests for database module.

Tests the db.py module which provides connection pool and query helpers.
"""

import json
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
                "INSERT INTO revision (branch_id, ifc_filename) VALUES (%s, %s) RETURNING revision_id",
                (branch_id, "test.ifc"),
            )
            rev_id = cur.fetchone()[0]
        
        # Verify data was committed
        with db.get_cursor() as cur:
            cur.execute("SELECT ifc_filename FROM revision WHERE revision_id = %s", (rev_id,))
            result = cur.fetchone()
        
        assert result == ("test.ifc",)
    
    def test_get_cursor_auto_rollback_on_error(self, db_pool, test_branch):
        """Test that cursor auto-rolls back on error."""
        branch_id = test_branch
        try:
            with db.get_cursor() as cur:
                cur.execute(
                    "INSERT INTO revision (branch_id, ifc_filename) VALUES (%s, %s)",
                    (branch_id, "test.ifc"),
                )
                # Cause an error
                cur.execute("SELECT * FROM nonexistent_table")
        except Exception:
            pass  # Expected to fail
        
        # Verify data was NOT committed
        with db.get_cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM revision")
            count = cur.fetchone()[0]
        
        assert count == 0


class TestProjectHelpers:
    """Test project and branch helper functions."""

    def test_create_project(self, db_pool):
        """Test creating a project with default branch."""
        project = db.create_project("My Project", "A description")

        assert project["project_id"] is not None
        assert project["name"] == "My Project"
        assert project["description"] == "A description"

        # Should have auto-created a 'main' branch
        branches = db.fetch_branches(project["project_id"])
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
        project = db.fetch_project(str(created["project_id"]))

        assert project is not None
        assert project["name"] == "Find Me"

    def test_create_branch(self, db_pool):
        """Test creating an additional branch."""
        project = db.create_project("Branch Test")
        branch = db.create_branch(str(project["project_id"]), "feature-x")

        assert branch["name"] == "feature-x"
        assert str(branch["project_id"]) == str(project["project_id"])

        branches = db.fetch_branches(project["project_id"])
        assert len(branches) == 2  # main + feature-x


class TestRevisionHelpers:
    """Test revision helper functions."""
    
    def test_get_latest_revision_seq_empty(self, db_pool, test_branch):
        """Test getting latest revision seq when database is empty."""
        rev_seq = db.get_latest_revision_seq(test_branch)
        
        assert rev_seq is None
    
    def test_get_latest_revision_seq_with_data(self, db_pool, test_branch):
        """Test getting latest revision seq with data.

        We only assert that the latest sequence is a positive integer and at
        least as large as the number of rows we insert here. Other tests may
        have already created revisions on the same branch, so the absolute
        value is not stable across the full suite.
        """
        branch_id = test_branch
        with db.get_cursor() as cur:
            cur.execute(
                "INSERT INTO revision (branch_id, ifc_filename) VALUES (%s, 'v1.ifc'), (%s, 'v2.ifc')",
                (branch_id, branch_id),
            )
        
        rev_seq = db.get_latest_revision_seq(branch_id)
        
        assert isinstance(rev_seq, int)
        assert rev_seq >= 2
    
    def test_fetch_revisions_empty(self, db_pool, test_branch):
        """Test fetching revisions when database is empty."""
        revisions = db.fetch_revisions(test_branch)
        
        assert isinstance(revisions, list)
        assert len(revisions) == 0
    
    def test_fetch_revisions_with_data(self, db_pool, test_branch):
        """Test fetching revisions with data."""
        branch_id = test_branch
        with db.get_cursor() as cur:
            cur.execute(
                "INSERT INTO revision (branch_id, commit_message, ifc_filename) VALUES "
                "(%s, 'Rev 1', 'v1.ifc'), (%s, 'Rev 2', 'v2.ifc')",
                (branch_id, branch_id),
            )
        
        revisions = db.fetch_revisions(branch_id)
        
        assert len(revisions) == 2
        assert revisions[0]["commit_message"] == "Rev 1"
        assert revisions[1]["commit_message"] == "Rev 2"
    
    def test_fetch_revisions_ordered(self, db_pool, test_branch):
        """Test that revisions are ordered by revision_seq ascending."""
        branch_id = test_branch
        with db.get_cursor() as cur:
            cur.execute(
                "INSERT INTO revision (branch_id, ifc_filename) VALUES "
                "(%s, 'v3.ifc'), (%s, 'v1.ifc'), (%s, 'v2.ifc')",
                (branch_id, branch_id, branch_id),
            )
        
        revisions = db.fetch_revisions(branch_id)
        
        assert revisions[0]["revision_seq"] < revisions[1]["revision_seq"] < revisions[2]["revision_seq"]


class TestProductQueries:
    """Test entity query functions."""
    
    @pytest.fixture
    def sample_products(self, db_pool, test_branch):
        """Create sample entities for testing. Returns (revision_seq, branch_id)."""
        branch_id = test_branch
        with db.get_cursor() as cur:
            cur.execute(
                "INSERT INTO revision (branch_id, ifc_filename) VALUES (%s, 'test.ifc') RETURNING revision_id, revision_seq",
                (branch_id,),
            )
            row = cur.fetchone()
            rev_id, rev_seq = row[0], row[1]
            cur.execute(
                """
                INSERT INTO ifc_entity 
                (branch_id, ifc_global_id, ifc_class, attributes, content_hash, created_in_revision_id)
                VALUES
                (%s, '0000000000000000000001', 'IfcWall', %s, 'hash1', %s),
                (%s, '0000000000000000000002', 'IfcSlab', %s, 'hash2', %s),
                (%s, '0000000000000000000003', 'IfcWall', %s, 'hash3', %s)
                """,
                (branch_id, json.dumps({"Name": "Wall-1"}), rev_id,
                 branch_id, json.dumps({"Name": "Slab-1"}), rev_id,
                 branch_id, json.dumps({"Name": "Wall-2"}), rev_id),
            )
        
        return rev_seq, branch_id
    
    def test_fetch_entity_at_revision(self, sample_products):
        """Test fetching single entity at revision."""
        rev_seq, branch_id = sample_products
        entity = db.fetch_entity_at_revision("0000000000000000000001", rev_seq, branch_id)
        
        assert entity is not None
        assert entity["ifc_global_id"] == "0000000000000000000001"
        assert entity["ifc_class"] == "IfcWall"
        assert entity.get("attributes") and entity["attributes"].get("Name") == "Wall-1"
    
    def test_fetch_entity_at_revision_not_found(self, sample_products):
        """Test fetching non-existent entity."""
        rev_seq, branch_id = sample_products
        entity = db.fetch_entity_at_revision("9999999999999999999999", rev_seq, branch_id)
        
        assert entity is None
    
    def test_fetch_entities_at_revision_all(self, sample_products):
        """Test fetching all entities at revision."""
        rev_seq, branch_id = sample_products
        entities = db.fetch_entities_at_revision(rev_seq, branch_id)
        
        assert len(entities) == 3
        global_ids = {e["ifc_global_id"] for e in entities}
        assert "0000000000000000000001" in global_ids
        assert "0000000000000000000002" in global_ids
        assert "0000000000000000000003" in global_ids
    
    def test_fetch_entities_at_revision_filter_by_class(self, sample_products):
        """Test fetching entities filtered by IFC class."""
        rev_seq, branch_id = sample_products
        entities = db.fetch_entities_at_revision(rev_seq, branch_id, ifc_class="IfcWall")
        
        assert len(entities) == 2
        for e in entities:
            assert e["ifc_class"] == "IfcWall"
    
    def test_fetch_entities_at_revision_filter_by_container(self, db_pool, test_branch):
        """Test fetching entities filtered by container."""
        branch_id = test_branch
        with db.get_cursor() as cur:
            cur.execute(
                "INSERT INTO revision (branch_id, ifc_filename) VALUES (%s, 'test.ifc') RETURNING revision_id, revision_seq",
                (branch_id,),
            )
            row = cur.fetchone()
            rev_id, rev_seq = row[0], row[1]
            cur.execute(
                """
                INSERT INTO ifc_entity 
                (branch_id, ifc_global_id, ifc_class, attributes, content_hash, created_in_revision_id)
                VALUES
                (%s, '0000000000000000000001', 'IfcBuildingStorey', %s, 'hash1', %s),
                (%s, '0000000000000000000002', 'IfcWall', %s, 'hash2', %s),
                (%s, '0000000000000000000003', 'IfcWall', %s, 'hash3', %s)
                """,
                (branch_id, json.dumps({"Name": "Level-1"}), rev_id,
                 branch_id, json.dumps({"Name": "Wall-1", "ContainedIn": "0000000000000000000001"}), rev_id,
                 branch_id, json.dumps({"Name": "Wall-2", "ContainedIn": "0000000000000000000001"}), rev_id),
            )
        
        entities = db.fetch_entities_at_revision(
            rev_seq, branch_id, contained_in="0000000000000000000001"
        )
        
        assert len(entities) == 2
        for e in entities:
            assert e.get("attributes") and e["attributes"].get("ContainedIn") == "0000000000000000000001"
    
    def test_fetch_spatial_container(self, db_pool, test_branch):
        """Test fetching spatial container for element."""
        branch_id = test_branch
        with db.get_cursor() as cur:
            cur.execute(
                "INSERT INTO revision (branch_id, ifc_filename) VALUES (%s, 'test.ifc') RETURNING revision_id, revision_seq",
                (branch_id,),
            )
            row = cur.fetchone()
            rev_id, rev_seq = row[0], row[1]
            cur.execute(
                """
                INSERT INTO ifc_entity 
                (branch_id, ifc_global_id, ifc_class, attributes, content_hash, created_in_revision_id)
                VALUES
                (%s, '0000000000000000000001', 'IfcBuildingStorey', %s, 'hash1', %s)
                """,
                (branch_id, json.dumps({"Name": "Level-1"}), rev_id),
            )
        
        container = db.fetch_spatial_container("0000000000000000000001", rev_seq, branch_id)
        
        assert container is not None
        assert container["ifc_global_id"] == "0000000000000000000001"
    
    def test_fetch_spatial_container_none(self, sample_products):
        """Test fetching container when none exists."""
        rev_seq, branch_id = sample_products
        container = db.fetch_spatial_container(None, rev_seq, branch_id)
        
        assert container is None

    def test_fetch_distinct_ifc_classes_at_revision(self, sample_products):
        """Test fetching distinct IFC classes visible at a revision."""
        rev_seq, branch_id = sample_products
        classes = db.fetch_distinct_ifc_classes_at_revision(rev_seq, branch_id)

        assert set(classes) == {"IfcWall", "IfcSlab"}


class TestSCDType2Queries:
    """Test SCD Type 2 time-travel queries (created_in / obsoleted_in revision)."""
    
    def test_scd_type_2_current_products(self, db_pool, test_branch):
        """Test querying current (non-closed) entities."""
        branch_id = test_branch
        with db.get_cursor() as cur:
            cur.execute(
                "INSERT INTO revision (branch_id, ifc_filename) VALUES (%s, 'v1.ifc') RETURNING revision_id, revision_seq",
                (branch_id,),
            )
            r1 = cur.fetchone()
            rev1_id, rev1_seq = r1[0], r1[1]
            cur.execute(
                "INSERT INTO revision (branch_id, ifc_filename) VALUES (%s, 'v2.ifc') RETURNING revision_id, revision_seq",
                (branch_id,),
            )
            r2 = cur.fetchone()
            rev2_id, rev2_seq = r2[0], r2[1]
            # Entity created in rev1, obsoleted in rev2
            cur.execute(
                """
                INSERT INTO ifc_entity 
                (branch_id, ifc_global_id, ifc_class, attributes, content_hash, created_in_revision_id, obsoleted_in_revision_id)
                VALUES (%s, '0000000000000000000001', 'IfcWall', %s, 'hash1', %s, %s)
                """,
                (branch_id, json.dumps({"Name": "Wall-1"}), rev1_id, rev2_id),
            )
            # Current version in rev2
            cur.execute(
                """
                INSERT INTO ifc_entity 
                (branch_id, ifc_global_id, ifc_class, attributes, content_hash, created_in_revision_id)
                VALUES (%s, '0000000000000000000001', 'IfcWall', %s, 'hash2', %s)
                """,
                (branch_id, json.dumps({"Name": "Wall-1-Updated"}), rev2_id),
            )
        
        entity = db.fetch_entity_at_revision("0000000000000000000001", rev2_seq, branch_id)
        
        assert entity is not None
        assert entity.get("attributes") and entity["attributes"].get("Name") == "Wall-1-Updated"
    
    def test_scd_type_2_historical_query(self, db_pool, test_branch):
        """Test querying historical state."""
        branch_id = test_branch
        with db.get_cursor() as cur:
            cur.execute(
                "INSERT INTO revision (branch_id, ifc_filename) VALUES (%s, 'v1.ifc') RETURNING revision_id, revision_seq",
                (branch_id,),
            )
            r1 = cur.fetchone()
            rev1_id, rev1_seq = r1[0], r1[1]
            cur.execute(
                "INSERT INTO revision (branch_id, ifc_filename) VALUES (%s, 'v2.ifc') RETURNING revision_id, revision_seq",
                (branch_id,),
            )
            r2 = cur.fetchone()
            rev2_id, rev2_seq = r2[0], r2[1]
            cur.execute(
                """
                INSERT INTO ifc_entity 
                (branch_id, ifc_global_id, ifc_class, attributes, content_hash, created_in_revision_id, obsoleted_in_revision_id)
                VALUES (%s, '0000000000000000000001', 'IfcWall', %s, 'hash1', %s, %s)
                """,
                (branch_id, json.dumps({"Name": "Wall-1"}), rev1_id, rev2_id),
            )
            cur.execute(
                """
                INSERT INTO ifc_entity 
                (branch_id, ifc_global_id, ifc_class, attributes, content_hash, created_in_revision_id)
                VALUES (%s, '0000000000000000000001', 'IfcWall', %s, 'hash2', %s)
                """,
                (branch_id, json.dumps({"Name": "Wall-1-Updated"}), rev2_id),
            )
        
        entity = db.fetch_entity_at_revision("0000000000000000000001", rev1_seq, branch_id)
        
        assert entity is not None
        assert entity.get("attributes") and entity["attributes"].get("Name") == "Wall-1"


class TestRevisionDiff:
    """Test revision diff functionality (revision_seq-based)."""
    
    def test_fetch_revision_diff_empty(self, db_pool, test_branch):
        """Test diff between two empty states."""
        branch_id = test_branch
        with db.get_cursor() as cur:
            cur.execute(
                "INSERT INTO revision (branch_id, ifc_filename) VALUES (%s, 'v1.ifc'), (%s, 'v2.ifc')",
                (branch_id, branch_id),
            )
        
        diff = db.fetch_revision_diff(1, 2, branch_id)
        
        assert diff["added"] == []
        assert diff["modified"] == []
        assert diff["deleted"] == []
    
    def test_fetch_revision_diff_added(self, db_pool, test_branch):
        """Test detecting added entities."""
        branch_id = test_branch
        with db.get_cursor() as cur:
            cur.execute(
                "INSERT INTO revision (branch_id, ifc_filename) VALUES (%s, 'v1.ifc') RETURNING revision_id, revision_seq",
                (branch_id,),
            )
            r1 = cur.fetchone()
            rev1_id, rev1_seq = r1[0], r1[1]
            cur.execute(
                "INSERT INTO revision (branch_id, ifc_filename) VALUES (%s, 'v2.ifc') RETURNING revision_id, revision_seq",
                (branch_id,),
            )
            r2 = cur.fetchone()
            rev2_id, rev2_seq = r2[0], r2[1]
            cur.execute(
                """
                INSERT INTO ifc_entity 
                (branch_id, ifc_global_id, ifc_class, attributes, content_hash, created_in_revision_id)
                VALUES (%s, '0000000000000000000001', 'IfcWall', %s, 'hash1', %s)
                """,
                (branch_id, json.dumps({"Name": "Wall-1"}), rev2_id),
            )
        
        diff = db.fetch_revision_diff(rev1_seq, rev2_seq, branch_id)
        
        assert len(diff["added"]) == 1
        assert diff["added"][0]["ifc_global_id"] == "0000000000000000000001"
        assert len(diff["modified"]) == 0
        assert len(diff["deleted"]) == 0
    
    def test_fetch_revision_diff_deleted(self, db_pool, test_branch):
        """Test detecting deleted entities."""
        branch_id = test_branch
        with db.get_cursor() as cur:
            cur.execute(
                "INSERT INTO revision (branch_id, ifc_filename) VALUES (%s, 'v1.ifc') RETURNING revision_id, revision_seq",
                (branch_id,),
            )
            r1 = cur.fetchone()
            rev1_id, rev1_seq = r1[0], r1[1]
            cur.execute(
                "INSERT INTO revision (branch_id, ifc_filename) VALUES (%s, 'v2.ifc') RETURNING revision_id, revision_seq",
                (branch_id,),
            )
            r2 = cur.fetchone()
            rev2_id, rev2_seq = r2[0], r2[1]
            cur.execute(
                """
                INSERT INTO ifc_entity 
                (branch_id, ifc_global_id, ifc_class, attributes, content_hash, created_in_revision_id, obsoleted_in_revision_id)
                VALUES (%s, '0000000000000000000001', 'IfcWall', %s, 'hash1', %s, %s)
                """,
                (branch_id, json.dumps({"Name": "Wall-1"}), rev1_id, rev2_id),
            )
        
        diff = db.fetch_revision_diff(rev1_seq, rev2_seq, branch_id)
        
        assert len(diff["added"]) == 0
        assert len(diff["modified"]) == 0
        assert len(diff["deleted"]) == 1
        assert diff["deleted"][0]["ifc_global_id"] == "0000000000000000000001"
    
    def test_fetch_revision_diff_modified(self, db_pool, test_branch):
        """Test detecting modified entities."""
        branch_id = test_branch
        with db.get_cursor() as cur:
            cur.execute(
                "INSERT INTO revision (branch_id, ifc_filename) VALUES (%s, 'v1.ifc') RETURNING revision_id, revision_seq",
                (branch_id,),
            )
            r1 = cur.fetchone()
            rev1_id, rev1_seq = r1[0], r1[1]
            cur.execute(
                "INSERT INTO revision (branch_id, ifc_filename) VALUES (%s, 'v2.ifc') RETURNING revision_id, revision_seq",
                (branch_id,),
            )
            r2 = cur.fetchone()
            rev2_id, rev2_seq = r2[0], r2[1]
            cur.execute(
                """
                INSERT INTO ifc_entity 
                (branch_id, ifc_global_id, ifc_class, attributes, content_hash, created_in_revision_id, obsoleted_in_revision_id)
                VALUES (%s, '0000000000000000000001', 'IfcWall', %s, 'hash1', %s, %s)
                """,
                (branch_id, json.dumps({"Name": "Wall-1"}), rev1_id, rev2_id),
            )
            cur.execute(
                """
                INSERT INTO ifc_entity 
                (branch_id, ifc_global_id, ifc_class, attributes, content_hash, created_in_revision_id)
                VALUES (%s, '0000000000000000000001', 'IfcWall', %s, 'hash2', %s)
                """,
                (branch_id, json.dumps({"Name": "Wall-1-Modified"}), rev2_id),
            )
        
        diff = db.fetch_revision_diff(rev1_seq, rev2_seq, branch_id)
        
        assert len(diff["added"]) == 0
        assert len(diff["modified"]) == 1
        assert diff["modified"][0]["ifc_global_id"] == "0000000000000000000001"
        assert len(diff["deleted"]) == 0
