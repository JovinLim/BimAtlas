"""Tests for sheet template CRUD and search."""

import pytest

from src import db


class TestSheetTemplateCRUD:
    """Test basic CRUD operations on sheet_template table."""

    def test_create_sheet_template(self, db_pool, test_project):
        project_id = str(test_project["project_id"])
        payload = {"entries": [], "formulas": {}, "lockedIds": []}
        row = db.create_sheet_template(project_id, "QS Template", payload)
        assert row["sheet_template_id"] is not None
        assert str(row["project_id"]) == project_id
        assert row["name"] == "QS Template"
        assert row["sheet"] == payload
        assert row["open"] is False

    def test_fetch_sheet_template(self, db_pool, test_project):
        project_id = str(test_project["project_id"])
        created = db.create_sheet_template(
            project_id, "Fetch Test", {"entries": [{"id": "e1"}]}
        )
        fetched = db.fetch_sheet_template(str(created["sheet_template_id"]))
        assert fetched is not None
        assert fetched["name"] == "Fetch Test"
        assert fetched["sheet"]["entries"][0]["id"] == "e1"

    def test_fetch_sheet_template_not_found(self, db_pool):
        assert db.fetch_sheet_template("00000000-0000-0000-0000-000000000000") is None

    def test_fetch_sheet_templates_for_project(self, db_pool, test_project):
        project_id = str(test_project["project_id"])
        db.create_sheet_template(project_id, "A", {})
        db.create_sheet_template(project_id, "B", {})
        rows = db.fetch_sheet_templates_for_project(project_id)
        assert len(rows) == 2
        names = {r["name"] for r in rows}
        assert names == {"A", "B"}

    def test_fetch_sheet_templates_empty(self, db_pool, test_project):
        rows = db.fetch_sheet_templates_for_project(str(test_project["project_id"]))
        assert rows == []


class TestSheetTemplateSearch:
    """Test search_sheet_templates with project scope."""

    def test_search_by_name(self, db_pool, test_project):
        project_id = str(test_project["project_id"])
        db.create_sheet_template(project_id, "Walls QS", {})
        db.create_sheet_template(project_id, "Doors QS", {})
        db.create_sheet_template(project_id, "Slabs Template", {})
        results = db.search_sheet_templates("QS", project_id)
        assert len(results) == 2
        names = {r["name"] for r in results}
        assert names == {"Walls QS", "Doors QS"}

    def test_search_case_insensitive(self, db_pool, test_project):
        project_id = str(test_project["project_id"])
        db.create_sheet_template(project_id, "Quantity Survey", {})
        results = db.search_sheet_templates("quantity", project_id)
        assert len(results) == 1
        assert results[0]["name"] == "Quantity Survey"

    def test_search_no_match(self, db_pool, test_project):
        project_id = str(test_project["project_id"])
        db.create_sheet_template(project_id, "Some Template", {})
        results = db.search_sheet_templates("nonexistent", project_id)
        assert results == []
