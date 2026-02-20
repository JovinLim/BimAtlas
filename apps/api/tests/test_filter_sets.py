"""Tests for filter set CRUD, search scoping, applied filter sets, and compound product filtering."""

import pytest

from src import db


class TestFilterSetCRUD:
    """Test basic CRUD operations on filter_sets table."""

    def test_create_filter_set(self, db_pool, test_branch):
        branch_id = test_branch
        fs = db.create_filter_set(
            branch_id, "Walls Only", "AND",
            [{"mode": "class", "ifcClass": "IfcWall"}],
        )
        assert fs["id"] is not None
        assert fs["branch_id"] == branch_id
        assert fs["name"] == "Walls Only"
        assert fs["logic"] == "AND"
        assert len(fs["filters"]) == 1
        assert fs["filters"][0]["ifcClass"] == "IfcWall"

    def test_create_filter_set_or_logic(self, db_pool, test_branch):
        fs = db.create_filter_set(
            test_branch, "Mixed OR", "OR",
            [
                {"mode": "class", "ifcClass": "IfcDoor"},
                {"mode": "attribute", "attribute": "name", "value": "Wall"},
            ],
        )
        assert fs["logic"] == "OR"
        assert len(fs["filters"]) == 2

    def test_fetch_filter_set(self, db_pool, test_branch):
        fs = db.create_filter_set(
            test_branch, "Test FS", "AND",
            [{"mode": "class", "ifcClass": "IfcSlab"}],
        )
        fetched = db.fetch_filter_set(fs["id"])
        assert fetched is not None
        assert fetched["name"] == "Test FS"

    def test_fetch_filter_set_not_found(self, db_pool):
        assert db.fetch_filter_set(99999) is None

    def test_update_filter_set_name(self, db_pool, test_branch):
        fs = db.create_filter_set(
            test_branch, "Old Name", "AND", [],
        )
        updated = db.update_filter_set(fs["id"], name="New Name")
        assert updated is not None
        assert updated["name"] == "New Name"
        assert updated["logic"] == "AND"

    def test_update_filter_set_logic(self, db_pool, test_branch):
        fs = db.create_filter_set(test_branch, "FS", "AND", [])
        updated = db.update_filter_set(fs["id"], logic="OR")
        assert updated is not None
        assert updated["logic"] == "OR"

    def test_update_filter_set_filters(self, db_pool, test_branch):
        fs = db.create_filter_set(test_branch, "FS", "AND", [])
        new_filters = [{"mode": "class", "ifcClass": "IfcBeam"}]
        updated = db.update_filter_set(fs["id"], filters_json=new_filters)
        assert updated is not None
        assert len(updated["filters"]) == 1

    def test_update_filter_set_not_found(self, db_pool):
        assert db.update_filter_set(99999, name="x") is None

    def test_delete_filter_set(self, db_pool, test_branch):
        fs = db.create_filter_set(test_branch, "To Delete", "AND", [])
        assert db.delete_filter_set(fs["id"]) is True
        assert db.fetch_filter_set(fs["id"]) is None

    def test_delete_filter_set_not_found(self, db_pool):
        assert db.delete_filter_set(99999) is False

    def test_fetch_filter_sets_for_branch(self, db_pool, test_branch):
        db.create_filter_set(test_branch, "FS A", "AND", [])
        db.create_filter_set(test_branch, "FS B", "OR", [])
        sets = db.fetch_filter_sets_for_branch(test_branch)
        assert len(sets) == 2
        names = {s["name"] for s in sets}
        assert names == {"FS A", "FS B"}

    def test_fetch_filter_sets_for_branch_empty(self, db_pool, test_branch):
        sets = db.fetch_filter_sets_for_branch(test_branch)
        assert sets == []


class TestFilterSetSearch:
    """Test search_filter_sets with scope narrowing."""

    def _make_two_projects(self):
        """Create two projects each with a branch and filter sets."""
        p1 = db.create_project("Project Alpha")
        p2 = db.create_project("Project Beta")
        b1 = db.fetch_branches(p1["id"])[0]["id"]
        b2 = db.fetch_branches(p2["id"])[0]["id"]
        db.create_filter_set(b1, "Walls Alpha", "AND", [])
        db.create_filter_set(b1, "Doors Alpha", "AND", [])
        db.create_filter_set(b2, "Walls Beta", "AND", [])
        return p1["id"], p2["id"], b1, b2

    def test_search_all_scopes(self, db_pool):
        self._make_two_projects()
        results = db.search_filter_sets("Walls")
        assert len(results) == 2

    def test_search_scoped_to_project(self, db_pool):
        p1_id, _, _, _ = self._make_two_projects()
        results = db.search_filter_sets("Walls", project_id=p1_id)
        assert len(results) == 1
        assert results[0]["name"] == "Walls Alpha"

    def test_search_scoped_to_branch(self, db_pool):
        _, _, b1, b2 = self._make_two_projects()
        results = db.search_filter_sets("Walls", branch_id=b2)
        assert len(results) == 1
        assert results[0]["name"] == "Walls Beta"

    def test_search_no_match(self, db_pool, test_branch):
        db.create_filter_set(test_branch, "Some Set", "AND", [])
        results = db.search_filter_sets("nonexistent")
        assert results == []

    def test_search_case_insensitive(self, db_pool, test_branch):
        db.create_filter_set(test_branch, "Wall Filters", "AND", [])
        results = db.search_filter_sets("wall")
        assert len(results) == 1


class TestAppliedFilterSets:
    """Test applying and fetching active filter sets per branch."""

    def test_apply_and_fetch(self, db_pool, test_branch):
        fs1 = db.create_filter_set(test_branch, "A", "AND", [])
        fs2 = db.create_filter_set(test_branch, "B", "OR", [])
        db.apply_filter_sets(test_branch, [fs1["id"], fs2["id"]], "AND")

        data = db.fetch_applied_filter_sets(test_branch)
        assert data["combination_logic"] == "AND"
        assert len(data["filter_sets"]) == 2
        ids = {fs["id"] for fs in data["filter_sets"]}
        assert ids == {fs1["id"], fs2["id"]}

    def test_apply_replaces_previous(self, db_pool, test_branch):
        fs1 = db.create_filter_set(test_branch, "A", "AND", [])
        fs2 = db.create_filter_set(test_branch, "B", "OR", [])

        db.apply_filter_sets(test_branch, [fs1["id"]], "AND")
        db.apply_filter_sets(test_branch, [fs2["id"]], "OR")

        data = db.fetch_applied_filter_sets(test_branch)
        assert data["combination_logic"] == "OR"
        assert len(data["filter_sets"]) == 1
        assert data["filter_sets"][0]["id"] == fs2["id"]

    def test_apply_empty_clears(self, db_pool, test_branch):
        fs1 = db.create_filter_set(test_branch, "A", "AND", [])
        db.apply_filter_sets(test_branch, [fs1["id"]], "AND")
        db.apply_filter_sets(test_branch, [], "AND")

        data = db.fetch_applied_filter_sets(test_branch)
        assert data["filter_sets"] == []
        assert data["combination_logic"] == "AND"

    def test_fetch_applied_empty_branch(self, db_pool, test_branch):
        data = db.fetch_applied_filter_sets(test_branch)
        assert data["filter_sets"] == []
        assert data["combination_logic"] == "AND"

    def test_delete_filter_set_cascades_applied(self, db_pool, test_branch):
        fs1 = db.create_filter_set(test_branch, "A", "AND", [])
        db.apply_filter_sets(test_branch, [fs1["id"]], "AND")
        db.delete_filter_set(fs1["id"])

        data = db.fetch_applied_filter_sets(test_branch)
        assert data["filter_sets"] == []


class TestProductFilterWithFilterSets:
    """Test fetch_products_with_filter_sets for compound AND/OR filtering."""

    @pytest.fixture(autouse=True)
    def _seed_products(self, db_pool, test_branch):
        """Insert a small set of products for filter testing."""
        self.branch_id = test_branch
        with db.get_cursor() as cur:
            cur.execute(
                "INSERT INTO revisions (branch_id, ifc_filename) VALUES (%s, %s) RETURNING id",
                (test_branch, "test.ifc"),
            )
            self.rev_id = cur.fetchone()[0]

            products = [
                ("g1", "IfcWall", "Exterior Wall", "Main wall", "BasicWall", "W1"),
                ("g2", "IfcDoor", "Front Door", "Entry door", "SingleDoor", "D1"),
                ("g3", "IfcWindow", "Side Window", None, "FixedWindow", "WN1"),
                ("g4", "IfcSlab", "Floor Slab", "Ground floor", "BasicSlab", "S1"),
                ("g5", "IfcWall", "Interior Wall", "Partition", "BasicWall", "W2"),
            ]
            for gid, cls, name, desc, otype, tag in products:
                cur.execute(
                    "INSERT INTO ifc_products "
                    "(branch_id, global_id, ifc_class, name, description, object_type, tag, "
                    "content_hash, valid_from_rev) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (test_branch, gid, cls, name, desc, otype, tag, f"hash-{gid}", self.rev_id),
                )

    def test_no_filter_sets_returns_all(self):
        rows = db.fetch_products_with_filter_sets(
            self.rev_id, self.branch_id, [], "AND",
        )
        assert len(rows) == 5

    def test_single_class_filter(self):
        rows = db.fetch_products_with_filter_sets(
            self.rev_id, self.branch_id,
            [{"logic": "AND", "filters": [{"mode": "class", "ifcClass": "IfcWall"}]}],
            "AND",
        )
        assert len(rows) == 2
        assert all(r["ifc_class"] == "IfcWall" for r in rows)

    def test_single_attribute_filter(self):
        rows = db.fetch_products_with_filter_sets(
            self.rev_id, self.branch_id,
            [{"logic": "AND", "filters": [{"mode": "attribute", "attribute": "name", "value": "Door"}]}],
            "AND",
        )
        assert len(rows) == 1
        assert rows[0]["global_id"] == "g2"

    def test_set_with_or_logic(self):
        """IfcWall OR name contains 'Door' -> 3 results (2 walls + 1 door)."""
        rows = db.fetch_products_with_filter_sets(
            self.rev_id, self.branch_id,
            [{
                "logic": "OR",
                "filters": [
                    {"mode": "class", "ifcClass": "IfcWall"},
                    {"mode": "attribute", "attribute": "name", "value": "Door"},
                ],
            }],
            "AND",
        )
        assert len(rows) == 3
        gids = {r["global_id"] for r in rows}
        assert gids == {"g1", "g2", "g5"}

    def test_multiple_sets_combined_with_and(self):
        """Set A (IfcWall) AND Set B (name contains 'Interior') -> 1 result."""
        rows = db.fetch_products_with_filter_sets(
            self.rev_id, self.branch_id,
            [
                {"logic": "AND", "filters": [{"mode": "class", "ifcClass": "IfcWall"}]},
                {"logic": "AND", "filters": [{"mode": "attribute", "attribute": "name", "value": "Interior"}]},
            ],
            "AND",
        )
        assert len(rows) == 1
        assert rows[0]["global_id"] == "g5"

    def test_multiple_sets_combined_with_or(self):
        """Set A (IfcDoor) OR Set B (IfcSlab) -> 2 results."""
        rows = db.fetch_products_with_filter_sets(
            self.rev_id, self.branch_id,
            [
                {"logic": "AND", "filters": [{"mode": "class", "ifcClass": "IfcDoor"}]},
                {"logic": "AND", "filters": [{"mode": "class", "ifcClass": "IfcSlab"}]},
            ],
            "OR",
        )
        assert len(rows) == 2
        gids = {r["global_id"] for r in rows}
        assert gids == {"g2", "g4"}

    def test_empty_filter_in_set_is_skipped(self):
        """Filters with missing values should be ignored."""
        rows = db.fetch_products_with_filter_sets(
            self.rev_id, self.branch_id,
            [{"logic": "AND", "filters": [{"mode": "attribute", "attribute": "name"}]}],
            "AND",
        )
        assert len(rows) == 5
