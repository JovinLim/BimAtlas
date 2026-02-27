"""Unit tests for the IFC4x3 schema loader utilities."""

import pytest

from src.schema import ifc_schema_loader as loader


@pytest.fixture(autouse=True)
def _require_schema(db_pool, ifc_schema_seeded):
    """Ensure schema is seeded before any loader test (loader reads from DB)."""
    pass


class TestEntityLookup:
    def test_get_entity_and_parent(self):
        """Basic sanity checks for entity presence and parent linkage."""
        ent = loader.get_entity("IfcWall")
        assert ent is not None
        assert ent["abstract"] is False
        # IfcWall should be a descendant of IfcBuiltElement / IfcElement / IfcProduct.
        parent = loader.get_parent("IfcWall")
        assert isinstance(parent, str)

        # Walk up the chain; must reach a product ancestor (IfcProduct/IfcObject/IfcRoot)
        # or at least IfcBuiltElement (parent linkage works).
        seen = set()
        current = "IfcWall"
        while current and current not in seen:
            seen.add(current)
            current = loader.get_parent(current) or ""
        product_ancestors = {"IfcProduct", "IfcObject", "IfcRoot"}
        assert seen & product_ancestors or "IfcBuiltElement" in seen, (
            f"Chain from IfcWall should reach a product ancestor or IfcBuiltElement; got: {seen}"
        )


class TestAttributeChains:
    def test_full_attribute_chain_contains_root_and_child_attrs(self):
        """Ensure full attribute chains include both root and child attributes."""
        attrs = loader.get_full_attribute_chain("IfcActorRole")
        names = [a["name"] for a in attrs]
        # IfcActorRole declares Role / UserDefinedRole / Description.
        assert "Role" in names
        assert "Description" in names
        # Rooted entities should pick up GlobalId from IfcRoot.
        root_attrs = loader.get_full_attribute_chain("IfcProduct")
        root_names = {a["name"] for a in root_attrs}
        assert "GlobalId" in root_names


class TestDescendants:
    def test_descendants_of_product_include_common_classes(self):
        """Descendants of IfcProduct should include common concrete product types."""
        desc = loader.get_descendants("IfcProduct", concrete_only=True)
        assert "IfcWall" in desc
        assert "IfcSlab" in desc
        # Abstract IfcProduct itself should not be in the concrete-only list.
        assert "IfcProduct" not in desc

