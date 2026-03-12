"""Unit tests for filter_tree canonicalization and validation (no DB required)."""

import pytest

from src.schema.filter_tree import (
    canonicalize_filters,
    validate_filter_tree,
)


class TestValidateFilterTree:
    """Test validate_filter_tree allows empty root but rejects empty subgroups."""

    def test_empty_root_allowed(self):
        """Empty root group is valid (create_filter_set before add_filter_condition)."""
        tree = {"kind": "group", "op": "ALL", "children": []}
        errs = validate_filter_tree(tree)
        assert errs == []

    def test_root_with_one_leaf_valid(self):
        tree = {
            "kind": "group",
            "op": "ALL",
            "children": [{"kind": "leaf", "mode": "class", "ifcClass": "IfcWall"}],
        }
        errs = validate_filter_tree(tree)
        assert errs == []

    def test_empty_subgroup_rejected(self):
        """Nested subgroup with no children is invalid."""
        tree = {
            "kind": "group",
            "op": "ALL",
            "children": [
                {"kind": "group", "op": "ANY", "children": []},
            ],
        }
        errs = validate_filter_tree(tree)
        assert any("must have at least one child" in e for e in errs)


class TestCanonicalizeFilters:
    """Test canonicalize_filters produces valid empty tree."""

    def test_empty_legacy_list_produces_valid_tree(self):
        tree = canonicalize_filters([], "AND")
        assert tree == {"kind": "group", "op": "ALL", "children": []}
        assert validate_filter_tree(tree) == []
