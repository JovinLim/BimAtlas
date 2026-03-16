"""Tests for app_views CRUD, BCF validation, and view_filter_sets aggregation."""

import pytest

from src import db

_BCF_PERSPECTIVE = {
    "perspective_camera": {
        "position": [10.0, 10.0, 10.0],
        "direction": [0.0, 0.0, -1.0],
        "up_vector": [0.0, 1.0, 0.0],
        "field_of_view": 60.0,
    },
}

_BCF_ORTHOGONAL = {
    "orthogonal_camera": {
        "position": [0.0, 0.0, 5.0],
        "direction": [0.0, 0.0, -1.0],
        "up_vector": [0.0, 1.0, 0.0],
        "view_to_world_scale": 1.0,
    },
}


class TestAppViewCRUD:
    """Test CRUD operations on app_views table."""

    def test_create_app_view_perspective(self, db_pool, test_branch):
        view = db.create_app_view(
            test_branch,
            "My View",
            _BCF_PERSPECTIVE,
            ui_filters={"level": [4, 5], "class": ["IfcWall"]},
        )
        assert view["id"] is not None
        assert str(view["branch_id"]) == str(test_branch)
        assert view["name"] == "My View"
        assert "perspective_camera" in view["bcf_camera_state"]
        assert view["ui_filters"]["level"] == [4, 5]

    def test_create_app_view_orthogonal(self, db_pool, test_branch):
        view = db.create_app_view(
            test_branch,
            "Ortho View",
            _BCF_ORTHOGONAL,
        )
        assert view["name"] == "Ortho View"
        assert "orthogonal_camera" in view["bcf_camera_state"]

    def test_create_app_view_invalid_bcf_rejected(self, db_pool, test_branch):
        with pytest.raises(ValueError, match="perspective_camera or orthogonal_camera"):
            db.create_app_view(test_branch, "Bad", {})

    def test_fetch_app_view(self, db_pool, test_branch):
        created = db.create_app_view(test_branch, "Fetch Test", _BCF_PERSPECTIVE)
        fetched = db.fetch_app_view(str(created["id"]))
        assert fetched is not None
        assert fetched["name"] == "Fetch Test"

    def test_fetch_app_view_not_found(self, db_pool):
        assert db.fetch_app_view("00000000-0000-0000-0000-000000000000") is None

    def test_fetch_app_views_for_branch(self, db_pool, test_branch):
        db.create_app_view(test_branch, "View A", _BCF_PERSPECTIVE)
        db.create_app_view(test_branch, "View B", _BCF_ORTHOGONAL)
        views = db.fetch_app_views_for_branch(test_branch)
        assert len(views) >= 2
        names = {v["name"] for v in views}
        assert "View A" in names and "View B" in names

    def test_update_app_view(self, db_pool, test_branch):
        view = db.create_app_view(test_branch, "Original", _BCF_PERSPECTIVE)
        updated = db.update_app_view(str(view["id"]), name="Updated")
        assert updated is not None
        assert updated["name"] == "Updated"

    def test_update_app_view_invalid_bcf_rejected(self, db_pool, test_branch):
        view = db.create_app_view(test_branch, "OK", _BCF_PERSPECTIVE)
        with pytest.raises(ValueError, match="perspective_camera or orthogonal_camera"):
            db.update_app_view(str(view["id"]), bcf_camera_state={})

    def test_delete_app_view(self, db_pool, test_branch):
        view = db.create_app_view(test_branch, "To Delete", _BCF_PERSPECTIVE)
        assert db.delete_app_view(str(view["id"])) is True
        assert db.fetch_app_view(str(view["id"])) is None


class TestAppViewAggregation:
    """Test fetch_app_view_with_filter_sets returns aggregated payload."""

    def test_fetch_with_filter_sets_empty(self, db_pool, test_branch):
        view = db.create_app_view(test_branch, "No Filters", _BCF_PERSPECTIVE)
        aggregated = db.fetch_app_view_with_filter_sets(str(view["id"]))
        assert aggregated is not None
        assert aggregated["filter_sets"] == []

    def test_fetch_with_filter_sets_linked(self, db_pool, test_branch):
        fs1 = db.create_filter_set(test_branch, "FS A", "AND", [])
        fs2 = db.create_filter_set(test_branch, "FS B", "OR", [])
        view = db.create_app_view(test_branch, "With Filters", _BCF_PERSPECTIVE)
        db.attach_filter_sets_to_view(str(view["id"]), [str(fs1["filter_set_id"]), str(fs2["filter_set_id"])])
        aggregated = db.fetch_app_view_with_filter_sets(str(view["id"]))
        assert aggregated is not None
        assert len(aggregated["filter_sets"]) == 2
        names = {fs["name"] for fs in aggregated["filter_sets"]}
        assert names == {"FS A", "FS B"}


class TestViewFilterSets:
    """Test view_filter_sets attach and fetch."""

    def test_attach_filter_sets(self, db_pool, test_branch):
        fs = db.create_filter_set(test_branch, "Attach FS", "AND", [])
        view = db.create_app_view(test_branch, "View", _BCF_PERSPECTIVE)
        db.attach_filter_sets_to_view(str(view["id"]), [str(fs["filter_set_id"])])
        ids = db.fetch_view_filter_set_ids(str(view["id"]))
        assert ids == [str(fs["filter_set_id"])]

    def test_attach_replaces_previous(self, db_pool, test_branch):
        fs1 = db.create_filter_set(test_branch, "FS1", "AND", [])
        fs2 = db.create_filter_set(test_branch, "FS2", "AND", [])
        view = db.create_app_view(test_branch, "View", _BCF_PERSPECTIVE)
        db.attach_filter_sets_to_view(str(view["id"]), [str(fs1["filter_set_id"])])
        db.attach_filter_sets_to_view(str(view["id"]), [str(fs2["filter_set_id"])])
        ids = db.fetch_view_filter_set_ids(str(view["id"]))
        assert ids == [str(fs2["filter_set_id"])]

    def test_attach_invalid_filter_set_raises(self, db_pool, test_branch):
        view = db.create_app_view(test_branch, "View", _BCF_PERSPECTIVE)
        with pytest.raises(ValueError, match="not found"):
            db.attach_filter_sets_to_view(str(view["id"]), ["00000000-0000-0000-0000-000000000000"])
