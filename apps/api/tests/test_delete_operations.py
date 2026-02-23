"""Tests for delete_project, delete_branch, and delete_revision."""

from src import db, config
from src.services.graph import age_client


def _count_graph_nodes_for_branch(branch_id: int) -> int:
    """Return the number of graph nodes with the given branch_id (test helper)."""
    bid = int(branch_id)  # ensure integer for safe embedding in Cypher
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("LOAD 'age';")
            cur.execute('SET search_path = ag_catalog, "$user", public;')
            sql = (
                f"SELECT * FROM cypher('{config.AGE_GRAPH}', "
                f"$$MATCH (n) WHERE n.branch_id = {bid} RETURN count(n) AS c$$) AS (c agtype)"
            )
            cur.execute(sql)
            row = cur.fetchone()
        conn.commit()
        if row and row[0] is not None:
            val = row[0]
            if isinstance(val, str) and val.isdigit():
                return int(val)
            if isinstance(val, (int, float)):
                return int(val)
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        db.put_conn(conn)


class TestDeleteProject:
    """Test delete_project."""

    def test_delete_project(self, db_pool):  # pylint: disable=unused-argument
        project = db.create_project("To Delete", "Will be removed")
        project_id = project["id"]
        assert db.fetch_project(project_id) is not None
        assert db.delete_project(project_id) is True
        assert db.fetch_project(project_id) is None
        assert db.fetch_branches(project_id) == []

    def test_delete_project_not_found(self, db_pool):  # pylint: disable=unused-argument
        assert db.delete_project(99999) is False

    def test_delete_project_cascades_branches(self, db_pool):  # pylint: disable=unused-argument
        project = db.create_project("With Branches")
        project_id = project["id"]
        db.create_branch(project_id, "extra")
        branches = db.fetch_branches(project_id)
        assert len(branches) == 2
        assert db.delete_project(project_id) is True
        assert db.fetch_branches(project_id) == []


class TestDeleteBranch:
    """Test delete_branch."""

    def test_delete_branch(self, db_pool, test_branch):  # pylint: disable=unused-argument
        branch_id = test_branch
        assert db.fetch_branch(branch_id) is not None
        assert db.delete_branch(branch_id) is True
        assert db.fetch_branch(branch_id) is None

    def test_delete_branch_not_found(self, db_pool):  # pylint: disable=unused-argument
        assert db.delete_branch(99999) is False

    def test_delete_branch_cascades_revisions_and_filter_sets(
        self, db_pool, test_branch  # pylint: disable=unused-argument
    ):
        branch_id = test_branch
        with db.get_cursor() as cur:
            cur.execute(
                "INSERT INTO revisions (branch_id, ifc_filename) VALUES (%s, %s) RETURNING id",
                (branch_id, "test.ifc"),
            )
            rev_id = cur.fetchone()[0]
        db.create_filter_set(branch_id, "FS", "AND", [])
        assert db.get_latest_revision_id(branch_id) == rev_id
        assert len(db.fetch_filter_sets_for_branch(branch_id)) == 1
        assert db.delete_branch(branch_id) is True
        assert db.fetch_branch(branch_id) is None


class TestDeleteRevision:
    """Test delete_revision."""

    def test_delete_revision(self, db_pool, test_branch):  # pylint: disable=unused-argument
        branch_id = test_branch
        with db.get_cursor() as cur:
            cur.execute(
                "INSERT INTO revisions (branch_id, ifc_filename) VALUES (%s, %s) RETURNING id",
                (branch_id, "test.ifc"),
            )
            rev_id = cur.fetchone()[0]
        assert db.fetch_revisions(branch_id)[0]["id"] == rev_id
        assert db.delete_revision(rev_id) is True
        assert db.fetch_revisions(branch_id) == []

    def test_delete_revision_not_found(self, db_pool):  # pylint: disable=unused-argument
        assert db.delete_revision(99999) is False

    def test_delete_revision_removes_products_valid_from_rev(
        self, db_pool, test_branch  # pylint: disable=unused-argument
    ):
        branch_id = test_branch
        with db.get_cursor() as cur:
            cur.execute(
                "INSERT INTO revisions (branch_id, ifc_filename) VALUES (%s, %s) RETURNING id",
                (branch_id, "test.ifc"),
            )
            rev_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO ifc_products (branch_id, global_id, ifc_class, name, content_hash, valid_from_rev) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (branch_id, "g1", "IfcWall", "Wall", "h1", rev_id),
            )
        assert db.delete_revision(rev_id) is True
        with db.get_cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM ifc_products WHERE branch_id = %s",
                (branch_id,),
            )
            assert cur.fetchone()[0] == 0


class TestDeleteGraphCleanup:
    """Test that AGE graph data is cleaned up on branch/project deletion."""

    def test_delete_branch_removes_graph_data(
        self, db_pool, age_graph, test_branch  # pylint: disable=unused-argument
    ):
        branch_id = test_branch
        age_client.create_node("IfcWall", "test-gid-1", "Test Wall", 1, branch_id)
        assert _count_graph_nodes_for_branch(branch_id) == 1
        assert db.delete_branch(branch_id) is True
        assert _count_graph_nodes_for_branch(branch_id) == 0

    def test_delete_project_removes_graph_data_for_all_branches(
        self, db_pool, age_graph  # pylint: disable=unused-argument
    ):
        project = db.create_project("Project With Graph")
        project_id = project["id"]
        branches = db.fetch_branches(project_id)
        main_branch_id = branches[0]["id"]
        db.create_branch(project_id, "other")
        branches = db.fetch_branches(project_id)
        other_branch_id = [b["id"] for b in branches if b["name"] == "other"][0]
        age_client.create_node("IfcWall", "g1", "Wall", 1, main_branch_id)
        age_client.create_node("IfcDoor", "g2", "Door", 1, other_branch_id)
        assert _count_graph_nodes_for_branch(main_branch_id) == 1
        assert _count_graph_nodes_for_branch(other_branch_id) == 1
        assert db.delete_project(project_id) is True
        assert _count_graph_nodes_for_branch(main_branch_id) == 0
        assert _count_graph_nodes_for_branch(other_branch_id) == 0
