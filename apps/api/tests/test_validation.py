"""Tests for the validation schema management feature (FEAT-004).

Tests entity CRUD, graph edge operations, validation engine, and GraphQL API.
"""

import json

import pytest

from src import db
from src.services.validation.engine import (
    RuleResult,
    _check_conditions,
    _resolve_nested_value,
    _MISSING,
    evaluate_rule,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_revision(branch_id: str) -> dict:
    """Create a revision and return {revision_id, revision_seq}."""
    return db.create_validation_revision(branch_id, "test revision")


def _insert_ifc_wall(branch_id: str, revision_id: str, global_id: str, attrs: dict) -> dict:
    """Insert an IfcWall entity for testing."""
    import hashlib

    ch = hashlib.sha256(
        json.dumps(attrs, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    with db.get_cursor(dict_cursor=True) as cur:
        cur.execute(
            "INSERT INTO ifc_entity "
            "(branch_id, ifc_global_id, ifc_class, attributes, content_hash, "
            " created_in_revision_id) "
            "VALUES (%s, %s, %s, %s, %s, %s) "
            "RETURNING entity_id, ifc_global_id, ifc_class, attributes",
            (branch_id, global_id, "IfcWall", json.dumps(attrs), ch, revision_id),
        )
        return dict(cur.fetchone())


# ---------------------------------------------------------------------------
# Validation entity CRUD
# ---------------------------------------------------------------------------


class TestValidationEntityCRUD:

    def test_create_validation_schema(self, db_pool, test_branch):
        rev = _make_revision(test_branch)
        entity = db.create_validation_entity(
            test_branch,
            rev["revision_id"],
            "IfcValidationSchema",
            {
                "Name": "Fire Safety", "Description": "Fire rules",
                "Version": "1.0", "IsActive": True,
            },
        )
        assert entity["ifc_class"] == "IfcValidationSchema"
        assert entity["ifc_global_id"]
        attrs = entity["attributes"]
        if isinstance(attrs, str):
            attrs = json.loads(attrs)
        assert attrs["Name"] == "Fire Safety"

    def test_create_validation_rule(self, db_pool, test_branch):
        rev = _make_revision(test_branch)
        entity = db.create_validation_entity(
            test_branch,
            rev["revision_id"],
            "IfcValidation",
            {
                "Name": "Wall Fire Rating",
                "TargetClass": "IfcWall",
                "Severity": "Error",
                "Conditions": [{
                    "path": "PropertySets.Pset_WallCommon.FireRating",
                    "operator": "equals", "value": "2hr",
                }],
            },
        )
        assert entity["ifc_class"] == "IfcValidation"

    def test_create_invalid_class_raises(self, db_pool, test_branch):
        rev = _make_revision(test_branch)
        with pytest.raises(ValueError, match="ifc_class must be one of"):
            db.create_validation_entity(
                test_branch, rev["revision_id"], "IfcWall", {"Name": "bad"},
            )

    def test_fetch_validation_entities(self, db_pool, test_branch):
        rev = _make_revision(test_branch)
        db.create_validation_entity(
            test_branch, rev["revision_id"], "IfcValidationSchema",
            {"Name": "Schema A"},
        )
        db.create_validation_entity(
            test_branch, rev["revision_id"], "IfcValidationSchema",
            {"Name": "Schema B"},
        )
        rows = db.fetch_validation_entities(test_branch, "IfcValidationSchema")
        assert len(rows) == 2

    def test_fetch_validation_entity_by_global_id(self, db_pool, test_branch):
        rev = _make_revision(test_branch)
        created = db.create_validation_entity(
            test_branch, rev["revision_id"], "IfcValidation",
            {"Name": "Test Rule"},
        )
        fetched = db.fetch_validation_entity(test_branch, created["ifc_global_id"])
        assert fetched is not None
        assert fetched["ifc_global_id"] == created["ifc_global_id"]

    def test_update_validation_entity(self, db_pool, test_branch):
        rev = _make_revision(test_branch)
        created = db.create_validation_entity(
            test_branch, rev["revision_id"], "IfcValidationSchema",
            {"Name": "Original"},
        )
        rev2 = _make_revision(test_branch)
        updated = db.update_validation_entity(
            test_branch, created["ifc_global_id"],
            rev2["revision_id"], {"Name": "Updated"},
        )
        assert updated is not None
        attrs = updated["attributes"]
        if isinstance(attrs, str):
            attrs = json.loads(attrs)
        assert attrs["Name"] == "Updated"

        # Old version should be obsoleted
        fetched = db.fetch_validation_entity(test_branch, created["ifc_global_id"])
        f_attrs = fetched["attributes"]
        if isinstance(f_attrs, str):
            f_attrs = json.loads(f_attrs)
        assert f_attrs["Name"] == "Updated"

    def test_delete_validation_entity(self, db_pool, test_branch):
        rev = _make_revision(test_branch)
        created = db.create_validation_entity(
            test_branch, rev["revision_id"], "IfcValidation",
            {"Name": "To Delete"},
        )
        rev2 = _make_revision(test_branch)
        assert db.delete_validation_entity(
            test_branch, created["ifc_global_id"], rev2["revision_id"],
        )
        fetched = db.fetch_validation_entity(test_branch, created["ifc_global_id"])
        assert fetched is None

    def test_create_validation_revision(self, db_pool, test_branch):
        rev = db.create_validation_revision(test_branch, "test change")
        assert "revision_id" in rev
        assert "revision_seq" in rev
        assert isinstance(rev["revision_seq"], int)


# ---------------------------------------------------------------------------
# Validation engine - operator tests
# ---------------------------------------------------------------------------


class TestValidationOperators:

    def test_resolve_nested_value(self):
        attrs = {"PropertySets": {"Pset_WallCommon": {"FireRating": "2hr"}}}
        assert _resolve_nested_value(attrs, "PropertySets.Pset_WallCommon.FireRating") == "2hr"
        assert _resolve_nested_value(attrs, "PropertySets.Pset_WallCommon") == {"FireRating": "2hr"}
        assert _resolve_nested_value(attrs, "Name") is _MISSING
        assert _resolve_nested_value(attrs, "PropertySets.Missing.Key") is _MISSING

    def test_check_conditions_pass(self):
        attrs = {
            "Name": "Wall-01",
            "PropertySets": {"Pset_WallCommon": {"FireRating": "2hr"}},
        }
        conditions = [
            {"path": "Name", "operator": "equals", "value": "Wall-01"},
            {
                "path": "PropertySets.Pset_WallCommon.FireRating",
                "operator": "equals", "value": "2hr",
            },
        ]
        assert _check_conditions(attrs, conditions) is None

    def test_check_conditions_fail(self):
        attrs = {
            "Name": "Wall-01",
            "PropertySets": {"Pset_WallCommon": {"FireRating": "1hr"}},
        }
        conditions = [
            {
                "path": "PropertySets.Pset_WallCommon.FireRating",
                "operator": "equals", "value": "2hr",
            },
        ]
        msg = _check_conditions(attrs, conditions)
        assert msg is not None
        assert "FireRating" in msg or "equals" in msg

    def test_check_conditions_exists(self):
        attrs = {"Name": "Wall-01"}
        assert _check_conditions(attrs, [{"path": "Name", "operator": "exists"}]) is None
        msg = _check_conditions(attrs, [{"path": "Description", "operator": "exists"}])
        assert msg is not None

    def test_check_conditions_not_exists(self):
        attrs = {"Name": "Wall-01"}
        assert _check_conditions(attrs, [{"path": "Description", "operator": "not_exists"}]) is None
        msg = _check_conditions(attrs, [{"path": "Name", "operator": "not_exists"}])
        assert msg is not None

    def test_check_conditions_contains(self):
        attrs = {"Name": "Wall-External-01"}
        cond_ext = [{"path": "Name", "operator": "contains",
                     "value": "External"}]
        assert _check_conditions(attrs, cond_ext) is None
        cond_int = [{"path": "Name", "operator": "contains",
                     "value": "Internal"}]
        msg = _check_conditions(attrs, cond_int)
        assert msg is not None

    def test_check_conditions_greater_than(self):
        attrs = {"Height": 3.0}
        cond_pass = [{"path": "Height", "operator": "greater_than",
                      "value": "2.5"}]
        assert _check_conditions(attrs, cond_pass) is None
        cond_fail = [{"path": "Height", "operator": "greater_than",
                      "value": "4.0"}]
        msg = _check_conditions(attrs, cond_fail)
        assert msg is not None

    def test_check_conditions_matches_regex(self):
        attrs = {"Tag": "W-001"}
        cond_pass = [{"path": "Tag", "operator": "matches",
                      "value": r"^W-\d+$"}]
        assert _check_conditions(attrs, cond_pass) is None
        cond_fail = [{"path": "Tag", "operator": "matches",
                      "value": r"^D-\d+$"}]
        msg = _check_conditions(attrs, cond_fail)
        assert msg is not None


# ---------------------------------------------------------------------------
# Validation engine - evaluate_rule
# ---------------------------------------------------------------------------


class TestEvaluateRule:

    def test_evaluate_rule_no_entities(self, db_pool, test_branch):
        _make_revision(test_branch)
        rule_attrs = {
            "Name": "Test Rule",
            "TargetClass": "IfcWall",
            "Severity": "Error",
            "Conditions": [{"path": "Name", "operator": "exists"}],
        }
        result = evaluate_rule("rule-1", rule_attrs, test_branch, 1)
        assert isinstance(result, RuleResult)
        assert result.passed is True
        assert len(result.violations) == 0

    def test_evaluate_rule_with_passing_entity(self, db_pool, test_branch):
        rev = _make_revision(test_branch)
        _insert_ifc_wall(test_branch, rev["revision_id"], "wall-001", {"Name": "Wall A"})
        rule_attrs = {
            "Name": "Name Exists",
            "TargetClass": "IfcWall",
            "Severity": "Warning",
            "Conditions": [{"path": "Name", "operator": "exists"}],
        }
        result = evaluate_rule("rule-2", rule_attrs, test_branch, rev["revision_seq"])
        assert result.passed is True

    def test_evaluate_rule_with_failing_entity(self, db_pool, test_branch):
        rev = _make_revision(test_branch)
        _insert_ifc_wall(test_branch, rev["revision_id"], "wall-002", {"Name": "Wall B"})
        rule_attrs = {
            "Name": "Has Description",
            "TargetClass": "IfcWall",
            "Severity": "Error",
            "Conditions": [{"path": "Description", "operator": "exists"}],
        }
        result = evaluate_rule("rule-3", rule_attrs, test_branch, rev["revision_seq"])
        assert result.passed is False
        assert len(result.violations) == 1
        assert result.violations[0].global_id == "wall-002"


# ---------------------------------------------------------------------------
# GraphQL API tests
# ---------------------------------------------------------------------------


class TestGraphQLValidation:

    def test_create_and_list_validation_schema(self, client, test_branch):
        response = client.post(
            "/graphql",
            json={
                "query": """
                    mutation($branchId: String!, $name: String!) {
                        createValidationSchema(branchId: $branchId, name: $name) {
                            globalId name description isActive
                        }
                    }
                """,
                "variables": {"branchId": test_branch, "name": "Test Schema"},
            },
        )
        data = response.json()
        assert "errors" not in data, f"GraphQL errors: {data.get('errors')}"
        schema = data["data"]["createValidationSchema"]
        assert schema["name"] == "Test Schema"
        assert schema["isActive"] is True

        # List schemas
        response = client.post(
            "/graphql",
            json={
                "query": """
                    query($branchId: String!) {
                        validationSchemas(branchId: $branchId) {
                            globalId name isActive
                            rules { globalId name }
                        }
                    }
                """,
                "variables": {"branchId": test_branch},
            },
        )
        data = response.json()
        assert "errors" not in data, f"GraphQL errors: {data.get('errors')}"
        schemas = data["data"]["validationSchemas"]
        assert len(schemas) >= 1
        assert any(s["name"] == "Test Schema" for s in schemas)

    def test_create_and_list_validation_rule(self, client, test_branch):
        response = client.post(
            "/graphql",
            json={
                "query": """
                    mutation(
                        $branchId: String!,
                        $name: String!,
                        $targetClass: String!,
                        $severity: String,
                        $conditions: [ValidationConditionInput!]
                    ) {
                        createValidationRule(
                            branchId: $branchId, name: $name,
                            targetClass: $targetClass,
                            severity: $severity,
                            conditions: $conditions
                        ) {
                            globalId name targetClass severity
                            conditions { path operator value }
                        }
                    }
                """,
                "variables": {
                    "branchId": test_branch,
                    "name": "Fire Rating Check",
                    "targetClass": "IfcWall",
                    "severity": "Error",
                    "conditions": [{
                        "path": "PropertySets.Pset_WallCommon.FireRating",
                        "operator": "equals",
                        "value": "2hr",
                    }],
                },
            },
        )
        data = response.json()
        assert "errors" not in data, f"GraphQL errors: {data.get('errors')}"
        rule = data["data"]["createValidationRule"]
        assert rule["name"] == "Fire Rating Check"
        assert rule["targetClass"] == "IfcWall"
        assert len(rule["conditions"]) == 1

        # List rules
        response = client.post(
            "/graphql",
            json={
                "query": """
                    query($branchId: String!) {
                        validationRules(branchId: $branchId) {
                            globalId name targetClass severity
                        }
                    }
                """,
                "variables": {"branchId": test_branch},
            },
        )
        data = response.json()
        assert "errors" not in data, f"GraphQL errors: {data.get('errors')}"
        rules = data["data"]["validationRules"]
        assert len(rules) >= 1

    def test_delete_validation_schema(self, client, test_branch):
        # Create
        resp = client.post(
            "/graphql",
            json={
                "query": """
                    mutation($branchId: String!, $name: String!) {
                        createValidationSchema(branchId: $branchId, name: $name) {
                            globalId
                        }
                    }
                """,
                "variables": {"branchId": test_branch, "name": "To Delete"},
            },
        )
        gid = resp.json()["data"]["createValidationSchema"]["globalId"]

        # Delete
        resp = client.post(
            "/graphql",
            json={
                "query": """
                    mutation($branchId: String!, $globalId: String!) {
                        deleteValidationSchema(branchId: $branchId, globalId: $globalId)
                    }
                """,
                "variables": {"branchId": test_branch, "globalId": gid},
            },
        )
        data = resp.json()
        assert "errors" not in data
        assert data["data"]["deleteValidationSchema"] is True

    def test_update_validation_schema(self, client, test_branch):
        resp = client.post(
            "/graphql",
            json={
                "query": """
                    mutation($branchId: String!, $name: String!) {
                        createValidationSchema(branchId: $branchId, name: $name) {
                            globalId name
                        }
                    }
                """,
                "variables": {"branchId": test_branch, "name": "Original Name"},
            },
        )
        gid = resp.json()["data"]["createValidationSchema"]["globalId"]

        resp = client.post(
            "/graphql",
            json={
                "query": """
                    mutation(
                        $branchId: String!,
                        $globalId: String!,
                        $name: String
                    ) {
                        updateValidationSchema(
                            branchId: $branchId,
                            globalId: $globalId,
                            name: $name
                        ) { globalId name }
                    }
                """,
                "variables": {"branchId": test_branch, "globalId": gid, "name": "Updated Name"},
            },
        )
        data = resp.json()
        assert "errors" not in data
        assert data["data"]["updateValidationSchema"]["name"] == "Updated Name"
