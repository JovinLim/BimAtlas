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
        def request(_method, _url, json=None, params=None):
            return FakeResponse()

    monkeypatch.setattr("src.services.agent.sandbox_tools.httpx.Client", FakeClient)

    result = execute_request("GET", "/agent/api-spec")
    assert result["status_code"] == 200
    assert result["truncated"] is True
    assert "notice" in result


def test_execute_request_rejects_invalid_method():
    with pytest.raises(ValueError, match="Unsupported method"):
        execute_request("CONNECT", "/agent/api-spec")
