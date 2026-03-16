"""Tests for agent API discovery, upload flow, and direct API request tools."""

import uuid

import pytest

from src.services.agent.sandbox_tools import MAX_RESPONSE_CHARS, execute_request


def test_agent_api_spec_exposes_graphql_schema_crud_examples(client):
    response = client.get("/agent/api-spec")
    assert response.status_code == 200
    data = response.json()
    assert data["graphql"]["endpoint"] == "/graphql"
    assert "examples" in data["graphql"]
    examples = data["graphql"]["examples"]["validation_schema_crud"]
    assert "create_uploaded_schema_rule_required_attributes" in examples
    assert "update_uploaded_schema_rule" in examples


def test_agent_api_spec_exposes_filter_set_examples_and_input_shape(client):
    response = client.get("/agent/api-spec")
    assert response.status_code == 200
    data = response.json()

    gql = data["graphql"]
    examples = gql["examples"]["filter_set_mutations"]
    assert "create_filter_set_with_flat_filters" in examples
    assert "create_filter_set_with_filters_tree" in examples
    assert "apply_filter_sets" in examples

    filter_input_fields = gql["input_objects"]["FilterInput"]
    by_name = {field["name"]: field["type"] for field in filter_input_fields}
    assert by_name["mode"] == "String!"
    assert by_name["ifcClass"] == "String"
    assert by_name["relationTargetClass"] == "String"


def test_agent_upload_accepts_pdf_and_stores_in_session(client):
    session_id = str(uuid.uuid4())
    response = client.post(
        "/agent/upload",
        data={"session_id": session_id},
        files={"file": ("regulation.pdf", b"%PDF-1.4\nfake", "application/pdf")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "regulation.pdf"
    assert body["session_id"] == session_id
    assert body["size_bytes"] > 0


def test_agent_upload_rejects_blocked_file_type(client):
    session_id = str(uuid.uuid4())
    response = client.post(
        "/agent/upload",
        data={"session_id": session_id},
        files={"file": ("payload.py", b"print('x')", "text/x-python")},
    )
    assert response.status_code == 400
    assert "Blocked file type" in response.json()["detail"]


def test_execute_request_returns_truncated_response(monkeypatch):
    class FakeResponse:
        status_code = 200
        is_success = True
        text = "z" * (MAX_RESPONSE_CHARS + 10)
        headers = {"content-type": "application/json"}

        @staticmethod
        def json():
            return {"ok": True}

    class FakeClient:
        def __init__(self, timeout: float):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        @staticmethod
        def request(_method, _url, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr("src.services.agent.sandbox_tools.httpx.Client", FakeClient)

    result = execute_request("GET", "/agent/api-spec")
    assert result["status_code"] == 200
    assert result["truncated"] is True
    assert "notice" in result


def test_execute_request_rejects_invalid_method():
    with pytest.raises(ValueError, match="Unsupported method"):
        execute_request("CONNECT", "/agent/api-spec")


def test_execute_request_publishes_filter_set_changed_for_create_filter_set(monkeypatch):
    class FakeResponse:
        status_code = 200
        is_success = True
        text = '{"data":{"createFilterSet":{"id":"fs-1"}}}'
        headers = {"content-type": "application/json"}

        @staticmethod
        def json():
            return {"data": {"createFilterSet": {"id": "fs-1"}}}

    class FakeClient:
        def __init__(self, timeout: float):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        @staticmethod
        def request(_method, _url, **_kwargs):
            return FakeResponse()

    calls: list[str] = []

    def fake_publish_filter_set_changed(branch_id: str) -> None:
        calls.append(branch_id)

    monkeypatch.setattr("src.services.agent.sandbox_tools.httpx.Client", FakeClient)
    monkeypatch.setattr(
        "src.services.agent.events.event_bus.publish_filter_set_changed",
        fake_publish_filter_set_changed,
    )

    execute_request(
        "POST",
        "/graphql",
        payload={
            "query": "mutation($branchId: String!) { createFilterSet(branchId: $branchId, name: \"A\", logic: \"AND\") { id } }",
            "variables": {"branchId": "branch-123"},
        },
    )
    assert calls == ["branch-123"]


def test_execute_request_publishes_filter_applied_for_apply_filter_sets(monkeypatch):
    class FakeResponse:
        status_code = 200
        is_success = True
        text = '{"data":{"applyFilterSets":{"combinationLogic":"AND"}}}'
        headers = {"content-type": "application/json"}

        @staticmethod
        def json():
            return {"data": {"applyFilterSets": {"combinationLogic": "AND"}}}

    class FakeClient:
        def __init__(self, timeout: float):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        @staticmethod
        def request(_method, _url, **_kwargs):
            return FakeResponse()

    calls: list[tuple[str, list[str], int]] = []

    def fake_publish_filter_applied(
        branch_id: str,
        filter_set_ids: list[str],
        matched_count: int,
    ) -> None:
        calls.append((branch_id, filter_set_ids, matched_count))

    monkeypatch.setattr("src.services.agent.sandbox_tools.httpx.Client", FakeClient)
    monkeypatch.setattr(
        "src.services.agent.events.event_bus.publish_filter_applied",
        fake_publish_filter_applied,
    )

    execute_request(
        "POST",
        "/graphql",
        payload={
            "query": "mutation($branchId: String!, $filterSetIds: [String!]!, $combinationLogic: String!) { applyFilterSets(branchId: $branchId, filterSetIds: $filterSetIds, combinationLogic: $combinationLogic) { combinationLogic } }",
            "variables": {
                "branchId": "branch-456",
                "filterSetIds": ["fs-1", "fs-2"],
                "combinationLogic": "AND",
            },
        },
    )
    assert calls == [("branch-456", ["fs-1", "fs-2"], 2)]
