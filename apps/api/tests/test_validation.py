"""Tests for the validation feature.

Tests validation_rule-based evaluation, operator helpers, and
IfcValidationResult persistence.
"""

import json

import pytest

from src import db
from src.services.validation.engine import (
    RuleResult,
    _check_conditions,
    _resolve_nested_value,
    _resolve_target_classes,
    _MISSING,
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
# Validation entity CRUD (IfcValidationResult only)
# ---------------------------------------------------------------------------


class TestValidationEntityCRUD:

    def test_create_validation_result(self, db_pool, test_branch):
        rev = _make_revision(test_branch)
        entity = db.create_validation_entity(
            test_branch,
            rev["revision_id"],
            "IfcValidationResult",
            {
                "Name": "Validation run: IFC4X3",
                "SchemaGlobalId": "some-schema-id",
                "Summary": {"errors": 0, "warnings": 1, "info": 0, "passed": 5},
            },
        )
        assert entity["ifc_class"] == "IfcValidationResult"
        assert entity["ifc_global_id"]
        attrs = entity["attributes"]
        if isinstance(attrs, str):
            attrs = json.loads(attrs)
        assert attrs["Name"] == "Validation run: IFC4X3"

    def test_create_invalid_class_raises(self, db_pool, test_branch):
        rev = _make_revision(test_branch)
        with pytest.raises(ValueError, match="ifc_class must be one of"):
            db.create_validation_entity(
                test_branch, rev["revision_id"], "IfcValidation", {"Name": "bad"},
            )

    def test_create_validation_revision(self, db_pool, test_branch):
        rev = db.create_validation_revision(test_branch, "test change")
        assert "revision_id" in rev
        assert "revision_seq" in rev
        assert isinstance(rev["revision_seq"], int)

    def test_fetch_validation_results(self, db_pool, test_branch):
        rev = _make_revision(test_branch)
        db.create_validation_entity(
            test_branch, rev["revision_id"], "IfcValidationResult",
            {"Name": "Result A"},
        )
        db.create_validation_entity(
            test_branch, rev["revision_id"], "IfcValidationResult",
            {"Name": "Result B"},
        )
        rows = db.fetch_validation_entities(test_branch, "IfcValidationResult")
        assert len(rows) == 2


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

    def test_resolve_target_classes_exact_only(self):
        """When include_inherited is False, only the target class is returned."""
        classes = _resolve_target_classes("IfcWall", False)
        assert classes == ["IfcWall"]

    def test_resolve_target_classes_include_inherited(self):
        """When include_inherited is True, target + descendants (if schema loaded)."""
        classes = _resolve_target_classes("IfcWall", True)
        # If IFC schema is loaded, IfcWall may have no concrete descendants; at least self.
        assert "IfcWall" in classes
        assert isinstance(classes, list)


# ---------------------------------------------------------------------------
# mv_entity_validations and fetch_validations_for_entities
# ---------------------------------------------------------------------------


class TestFetchValidationsForEntities:
    """Test that fetch_validations_for_entities reads from mv_entity_validations."""

    def test_fetch_validations_returns_data_from_mv(
        self, db_pool, test_branch
    ):
        """When MV has rows, fetch_validations_for_entities returns them."""
        import uuid

        rev = db.create_validation_revision(test_branch, "test")
        rev_id = rev["revision_id"]
        rev_seq = rev["revision_seq"]

        # Create ifc_schema and validation_rule (required for MV join)
        with db.get_cursor(dict_cursor=True) as cur:
            cur.execute(
                "INSERT INTO ifc_schema (schema_id, version_name) VALUES (%s, %s) RETURNING schema_id",
                (str(uuid.uuid4()), "TestSchema_MV"),
            )
            schema_row = cur.fetchone()
            schema_id = str(schema_row["schema_id"])
            rule_id = str(uuid.uuid4())
            cur.execute(
                """
                INSERT INTO validation_rule (
                    rule_id, version, name, schema_id, project_id, target_ifc_class,
                    rule_schema, severity, is_active
                ) VALUES (%s, 1, 'Test Rule', %s, NULL, 'IfcWall', %s, 'Error', TRUE)
                """,
                (rule_id, schema_id, json.dumps({"ruleType": "attribute_check", "Conditions": []})),
            )

        # Create IfcValidationResults entity (source for MV)
        entity_global_id = "3D2MqX8P1F9xK$nZ0R5wQ"
        result_attrs = {
            "SchemaGlobalId": schema_id,
            "SchemaName": "TestSchema_MV",
            "TargetRevisionSeq": rev_seq,
            "rule_id": rule_id,
            "rule_version": 1,
            "results": {
                "failed_global_ids": [],
                "passed_global_ids": [entity_global_id],
            },
        }
        db.create_validation_entity(
            test_branch, rev_id, "IfcValidationResults", result_attrs,
        )

        db.refresh_mv_entity_validations()

        val_map = db.fetch_validations_for_entities(
            test_branch, rev_seq, [entity_global_id],
        )
        assert entity_global_id in val_map
        validations = val_map[entity_global_id]
        assert isinstance(validations, dict)
        assert rule_id in validations
        rule_result = validations[rule_id]
        assert rule_result.get("passed") is True
        assert rule_result.get("ruleName") == "Test Rule"
        assert rule_result.get("schemaName") == "TestSchema_MV"
