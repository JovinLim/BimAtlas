"""Tests for the MCP tool layer (FEAT-004 Agentic Filtering Framework).

These tests verify the MCP tools that wrap existing DB functions:
  1. get_project_schema
  2. create_filter_set
  3. add_filter_condition
  4. add_filter_group
  5. apply_filter_set_to_context
"""

import json

import pytest

from src import db
from src.services.agent.mcp_tools import (
    add_filter_condition,
    add_filter_group,
    apply_filter_set_to_context,
    create_filter_set,
    get_project_schema,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_revision(branch_id: str) -> tuple[str, int]:
    """Insert a revision row and return (revision_id, revision_seq)."""
    with db.get_cursor(dict_cursor=True) as cur:
        cur.execute(
            "INSERT INTO revision (branch_id, ifc_filename) "
            "VALUES (%s, 'test.ifc') RETURNING revision_id, revision_seq",
            (branch_id,),
        )
        row = cur.fetchone()
    return str(row["revision_id"]), int(row["revision_seq"])


def _insert_entity(
    branch_id: str,
    revision_id: str,
    global_id: str,
    ifc_class: str,
    attributes: dict | None = None,
) -> None:
    """Insert a single ifc_entity row."""
    with db.get_cursor() as cur:
        cur.execute(
            "INSERT INTO ifc_entity "
            "(branch_id, ifc_global_id, ifc_class, attributes, content_hash, created_in_revision_id) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (
                branch_id,
                global_id,
                ifc_class,
                json.dumps(attributes or {}),
                f"hash-{global_id}",
                revision_id,
            ),
        )


# ---------------------------------------------------------------------------
# get_project_schema
# ---------------------------------------------------------------------------

class TestGetProjectSchema:
    def test_returns_classes_and_attributes(self, test_branch):
        rev_id, rev = _create_revision(test_branch)

        _insert_entity(test_branch, rev_id, "w1", "IfcWall", {"Name": "Wall-1", "FireRating": "2HR"})
        _insert_entity(test_branch, rev_id, "d1", "IfcDoor", {"Name": "Door-1"})

        result = get_project_schema(test_branch, revision=rev)

        assert "IfcWall" in result["ifc_classes"]
        assert "IfcDoor" in result["ifc_classes"]
        assert result["entity_count"] == 2
        assert "Name" in result["common_attributes"]
        assert "string" in result["filter_operators"]
        assert "numeric" in result["filter_operators"]
        assert "class" in result["filter_operators"]
        assert "object" in result["attribute_value_types"]
        assert result["attribute_value_type_hints"]["PropertySets"] == "object"
        assert "inherits_from" in result["filter_operators"]["class"]
        assert len(result["relationship_types"]) > 0

    def test_empty_branch(self, test_branch):
        _rev_id, rev = _create_revision(test_branch)
        result = get_project_schema(test_branch, revision=rev)
        assert result["ifc_classes"] == []
        assert result["entity_count"] == 0

    def test_invalid_branch_raises(self, db_pool):
        with pytest.raises(ValueError, match="Invalid branch_id"):
            get_project_schema("not-a-uuid")


# ---------------------------------------------------------------------------
# create_filter_set
# ---------------------------------------------------------------------------

class TestCreateFilterSet:
    def test_creates_empty_filter_set(self, test_branch):
        result = create_filter_set(test_branch, "Test Set", "AND")
        assert result["filter_set_id"]
        assert result["name"] == "Test Set"
        assert result["logic"] == "AND"
        assert result["filters"] == []
        assert result["filters_tree"]["kind"] == "group"
        assert result["filters_tree"]["children"] == []

    def test_defaults_to_and_logic(self, test_branch):
        result = create_filter_set(test_branch, "Default Logic")
        assert result["logic"] == "AND"

    def test_or_logic(self, test_branch):
        result = create_filter_set(test_branch, "OR Set", "OR")
        assert result["logic"] == "OR"

    def test_invalid_branch_raises(self, db_pool):
        with pytest.raises(ValueError, match="Invalid branch_id"):
            create_filter_set("bad-uuid", "Test")


# ---------------------------------------------------------------------------
# add_filter_condition
# ---------------------------------------------------------------------------

class TestAddFilterCondition:
    def test_add_class_condition(self, test_branch):
        fs = create_filter_set(test_branch, "Class Filter")
        result = add_filter_condition(
            fs["filter_set_id"], mode="class", operator="is", ifc_class="IfcWall",
        )
        assert result["condition_count"] == 1
        assert result["filters"][0]["mode"] == "class"
        assert result["filters"][0]["operator"] == "is"
        assert result["filters"][0]["ifcClass"] == "IfcWall"
        assert result["filters_tree"]["kind"] == "group"
        assert result["filters_tree"]["children"][0]["ifcClass"] == "IfcWall"

    def test_add_inherits_from(self, test_branch):
        fs = create_filter_set(test_branch, "Inheritance Filter")
        result = add_filter_condition(
            fs["filter_set_id"], mode="class", operator="inherits_from", ifc_class="IfcWindow",
        )
        assert result["condition_count"] == 1
        assert result["filters"][0]["operator"] == "inherits_from"

    def test_add_attribute_condition(self, test_branch):
        fs = create_filter_set(test_branch, "Attr Filter")
        result = add_filter_condition(
            fs["filter_set_id"],
            mode="attribute", operator="contains", attribute="Name", value="Wall",
        )
        assert result["condition_count"] == 1
        assert result["filters"][0]["attribute"] == "Name"

    def test_add_numeric_condition(self, test_branch):
        fs = create_filter_set(test_branch, "Numeric Filter")
        result = add_filter_condition(
            fs["filter_set_id"],
            mode="attribute", operator="gt", attribute="FireRating",
            value="2", value_type="numeric",
        )
        assert result["filters"][0]["valueType"] == "numeric"
        assert result["filters"][0]["operator"] == "gt"

    def test_multiple_conditions(self, test_branch):
        fs = create_filter_set(test_branch, "Multi Filter")
        add_filter_condition(fs["filter_set_id"], "class", "is", ifc_class="IfcWall")
        result = add_filter_condition(
            fs["filter_set_id"], "attribute", "contains", attribute="Name", value="ext",
        )
        assert result["condition_count"] == 2

    def test_normalizes_value_type_case(self, test_branch):
        fs = create_filter_set(test_branch, "Normalize ValueType")
        result = add_filter_condition(
            fs["filter_set_id"],
            mode="attribute",
            operator="contains",
            attribute="PropertySets",
            value="Pset_WallCommon",
            value_type="Object",
        )
        assert result["filters"][0]["valueType"] == "object"

    def test_infers_object_for_propertysets(self, test_branch):
        fs = create_filter_set(test_branch, "Infer PropertySets")
        result = add_filter_condition(
            fs["filter_set_id"],
            mode="attribute",
            operator="contains",
            attribute="PropertySets",
            value="Pset_WallCommon",
        )
        assert result["filters"][0]["valueType"] == "object"

    def test_invalid_value_type_raises(self, test_branch):
        fs = create_filter_set(test_branch, "Bad ValueType")
        with pytest.raises(ValueError, match="Invalid value_type"):
            add_filter_condition(
                fs["filter_set_id"],
                mode="attribute",
                operator="contains",
                attribute="Name",
                value="Wall",
                value_type="boolean",
            )

    def test_invalid_mode_raises(self, test_branch):
        fs = create_filter_set(test_branch, "Bad Mode")
        with pytest.raises(ValueError, match="Invalid mode"):
            add_filter_condition(fs["filter_set_id"], "badmode", "is")

    def test_invalid_operator_raises(self, test_branch):
        fs = create_filter_set(test_branch, "Bad Op")
        with pytest.raises(ValueError, match="Invalid operator"):
            add_filter_condition(fs["filter_set_id"], "class", "badop", ifc_class="IfcWall")

    def test_missing_class_raises(self, test_branch):
        fs = create_filter_set(test_branch, "No Class")
        with pytest.raises(ValueError, match="ifc_class is required"):
            add_filter_condition(fs["filter_set_id"], "class", "is")

    def test_missing_attribute_raises(self, test_branch):
        fs = create_filter_set(test_branch, "No Attr")
        with pytest.raises(ValueError, match="attribute is required"):
            add_filter_condition(fs["filter_set_id"], "attribute", "contains")

    def test_nonexistent_filter_set_raises(self, db_pool):
        fake_id = "00000000-0000-0000-0000-000000000000"
        with pytest.raises(ValueError, match="not found"):
            add_filter_condition(fake_id, "class", "is", ifc_class="IfcWall")

    def test_add_condition_to_nested_group(self, test_branch):
        """Add condition with parent_path to a group created by add_filter_group."""
        fs = create_filter_set(test_branch, "Nested", logic="AND")
        add_filter_condition(fs["filter_set_id"], "class", "is", ifc_class="IfcWall")
        grp = add_filter_group(
            fs["filter_set_id"],
            op="OR",
            mode="attribute",
            operator="contains",
            attribute="Name",
            value="Core",
            value_type="string",
        )
        assert "group_index" in grp
        assert grp["group_index"] == 1  # root has [leaf, group]
        result = add_filter_condition(
            fs["filter_set_id"],
            mode="attribute",
            operator="is",
            attribute="Tag",
            value="A1",
            value_type="string",
            parent_path=str(grp["group_index"]),
        )
        assert result["condition_count"] == 3
        tree = result["filters_tree"]
        assert tree["kind"] == "group"
        assert len(tree["children"]) == 2  # leaf + group
        sub = tree["children"][1]
        assert sub["kind"] == "group"
        assert sub["op"] == "ANY"
        assert len(sub["children"]) == 2  # Core, A1

    def test_invalid_parent_path_raises(self, test_branch):
        fs = create_filter_set(test_branch, "Bad Path")
        with pytest.raises(ValueError, match="parent_path|No child at index"):
            add_filter_condition(
                fs["filter_set_id"],
                "class", "is", ifc_class="IfcWall",
                parent_path="99",
            )
        with pytest.raises(ValueError, match="not a group"):
            add_filter_condition(
                fs["filter_set_id"],
                "class", "is", ifc_class="IfcWall",
            )
            add_filter_condition(
                fs["filter_set_id"],
                "class", "is", ifc_class="IfcDoor",
                parent_path="0",  # index 0 is a leaf, not a group
            )


# ---------------------------------------------------------------------------
# add_filter_group
# ---------------------------------------------------------------------------

class TestAddFilterGroup:
    def test_creates_nested_group_with_first_condition(self, test_branch):
        fs = create_filter_set(test_branch, "Group Test", logic="AND")
        result = add_filter_group(
            fs["filter_set_id"],
            op="OR",
            mode="class",
            operator="is",
            ifc_class="IfcDoor",
        )
        assert result["group_index"] == 0
        assert result["condition_count"] == 1
        tree = result["filters_tree"]
        assert tree["children"][0]["kind"] == "group"
        assert tree["children"][0]["op"] == "ANY"
        assert tree["children"][0]["children"][0]["ifcClass"] == "IfcDoor"

    def test_nested_tree_via_tools_matches_expected(self, test_branch):
        """Build ALL(IfcWall, ANY(Name contains Interior, Tag is W2)) via MCP tools."""
        rev_id, rev_seq = _create_revision(test_branch)
        products = [
            ("g1", "IfcWall", "Exterior Wall", "W1"),
            ("g5", "IfcWall", "Interior Wall", "W2"),
            ("g2", "IfcDoor", "Front Door", "D1"),
        ]
        for gid, cls, name, tag in products:
            _insert_entity(
                test_branch, rev_id, gid, cls,
                {"Name": name, "Tag": tag},
            )

        fs = create_filter_set(test_branch, "Nested Walls", logic="AND")
        add_filter_condition(fs["filter_set_id"], "class", "is", ifc_class="IfcWall")
        grp = add_filter_group(
            fs["filter_set_id"],
            op="OR",
            mode="attribute",
            operator="contains",
            attribute="Name",
            value="Interior",
            value_type="string",
        )
        add_filter_condition(
            fs["filter_set_id"],
            mode="attribute",
            operator="is",
            attribute="Tag",
            value="W2",
            value_type="string",
            parent_path=str(grp["group_index"]),
        )

        row = db.fetch_filter_set(fs["filter_set_id"])
        filter_sets_data = [{"logic": row["logic"], "filters": row["filters"]}]
        rows = db.fetch_entities_with_filter_sets(
            rev_seq, test_branch, filter_sets_data, "AND",
        )
        assert len(rows) == 1
        assert rows[0]["ifc_global_id"] == "g5"


# ---------------------------------------------------------------------------
# apply_filter_set_to_context
# ---------------------------------------------------------------------------

class TestApplyFilterSetToContext:
    def test_apply_single_set(self, test_branch):
        fs = create_filter_set(test_branch, "Apply Test")
        add_filter_condition(fs["filter_set_id"], "class", "is", ifc_class="IfcWall")
        result = apply_filter_set_to_context(test_branch, [fs["filter_set_id"]])
        assert result["combination_logic"] == "OR"
        assert len(result["applied_filter_sets"]) == 1
        assert result["applied_filter_sets"][0]["name"] == "Apply Test"
        assert result["applied_filter_sets"][0]["filters_tree"]["kind"] == "group"
        assert result["matched_entity_count"] >= 0

    def test_forces_or_logic(self, test_branch):
        fs = create_filter_set(test_branch, "Logic Test")
        result = apply_filter_set_to_context(
            test_branch, [fs["filter_set_id"]], combination_logic="AND",
        )
        assert result["combination_logic"] == "OR"

    def test_apply_with_entities(self, test_branch):
        rev_id, _rev = _create_revision(test_branch)
        _insert_entity(test_branch, rev_id, "w1", "IfcWall", {"Name": "W1"})
        _insert_entity(test_branch, rev_id, "w2", "IfcWall", {"Name": "W2"})
        _insert_entity(test_branch, rev_id, "d1", "IfcDoor", {"Name": "D1"})

        fs = create_filter_set(test_branch, "Wall Filter")
        add_filter_condition(fs["filter_set_id"], "class", "is", ifc_class="IfcWall")
        result = apply_filter_set_to_context(test_branch, [fs["filter_set_id"]])
        assert result["matched_entity_count"] == 2

    def test_invalid_branch_raises(self, db_pool):
        with pytest.raises(ValueError, match="Invalid branch_id"):
            apply_filter_set_to_context("bad-uuid", ["some-id"])


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

class TestToolRegistry:
    def test_get_agent_tools_includes_nested_tree_tools(self, test_branch):
        from src.services.agent.mcp_tools import get_agent_tools
        tools = get_agent_tools(test_branch, revision=None)
        assert len(tools) == 5
        names = {t.metadata.name for t in tools}
        assert names == {
            "get_project_schema",
            "create_filter_set",
            "add_filter_condition",
            "add_filter_group",
            "apply_filter_set_to_context",
        }
