"""Tests for IFC skill guardrails: search_skills, ask_user_for_guidance, save_ifc_skill."""

import uuid

import pytest

from src.services.agent.sandbox_tools import ask_user_for_guidance
from src.services.agent.skills import extract_frontmatter


def test_ask_user_for_guidance_returns_guidance_request():
    result = ask_user_for_guidance(
        question="What is the IFC path for elements contained in a storey?",
        context="User asked for ground floor windows",
    )
    assert result["type"] == "guidance_request"
    assert "storey" in result["question"].lower()
    assert "ground floor windows" in result["context"]
    assert "paused" in result["message"].lower()


def test_extract_frontmatter_parses_yaml():
    text = """---
name: spatial-filter
description: Filter by IfcBuildingStorey
ifcPath: IfcRelContainedInSpatialStructure
---
# Body
Some markdown content here.
"""
    fm, body = extract_frontmatter(text)
    assert fm.get("name") == "spatial-filter"
    assert fm.get("ifcPath") == "IfcRelContainedInSpatialStructure"
    assert "Some markdown content" in body


def test_extract_frontmatter_empty_input():
    fm, body = extract_frontmatter("")
    assert fm == {}
    assert body == ""


def test_extract_frontmatter_no_frontmatter():
    text = "Just plain markdown without frontmatter."
    fm, body = extract_frontmatter(text)
    assert fm == {}
    assert body == text


def test_discover_api_includes_ifc_cheat_sheet():
    from src.services.agent.api_spec import build_agent_api_spec
    from src.main import app
    from src.main import schema

    spec = build_agent_api_spec(app, schema)
    assert "ifc_cheat_sheet" in spec
    cheat = spec["ifc_cheat_sheet"]
    assert "directive" in cheat
    assert "relational_paths" in cheat
    assert "spatial_containment" in cheat["relational_paths"]
    assert "filter_modes" in cheat
    assert "anti_patterns" in cheat
    assert "IfcRelContainedInSpatialStructure" in str(cheat)


def test_search_skills_tool_fails_without_embedding_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from src.services.agent.sandbox_tools import search_skills

    with pytest.raises(ValueError, match="API key required|Embedding"):
        search_skills(
            "ground floor windows",
            project_id=str(uuid.uuid4()),
            branch_id=None,
            api_key=None,
        )


def test_get_api_tools_includes_skill_tools():
    from src.services.agent.sandbox_tools import get_api_tools

    def fake_spec():
        return {"paths": {}, "graphql": {}}

    tools = get_api_tools(
        str(uuid.uuid4()),
        fake_spec,
        include_discover=True,
        branch_id=str(uuid.uuid4()),
        project_id=str(uuid.uuid4()),
    )
    names = [t.metadata.name for t in tools]
    assert "search_skills" in names
    assert "ask_user_for_guidance" in names
    assert "save_ifc_skill" in names
    assert "discover_api" in names
    assert "execute_request" in names


def test_agent_skills_search_requires_intent_and_project(client):
    response = client.post("/agent/skills/search", json={})
    assert response.status_code == 400
    assert "intent" in response.json()["detail"].lower() or "projectid" in response.json()["detail"].lower()


def test_agent_skills_create_requires_title_intent_project(client):
    response = client.post("/agent/skills", json={})
    assert response.status_code == 400
    detail = response.json()["detail"].lower()
    assert "projectid" in detail or "title" in detail or "intent" in detail
