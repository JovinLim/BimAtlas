"""Unit tests for upload storage and direct API request tools."""

import uuid

import pytest

from src.services.agent.sandbox import SandboxManager
from src.services.agent.sandbox_tools import MAX_RESPONSE_CHARS, discover_api, execute_request


def test_sandbox_upload_type_validation(tmp_path):
    manager = SandboxManager(root_dir=tmp_path)
    sid = str(uuid.uuid4())
    with pytest.raises(ValueError, match="Unsupported file type"):
        manager.save_upload(sid, "payload.bin", b"abc")


def test_execute_request_truncates_large_responses(monkeypatch):
    large_text = "x" * (MAX_RESPONSE_CHARS + 25)

    class FakeResponse:
        status_code = 200
        is_success = True
        text = large_text
        headers = {"content-type": "text/plain"}

        @staticmethod
        def json():
            raise ValueError("not-json")

    class FakeClient:
        def __init__(self, timeout: float):
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        @staticmethod
        def request(_method, _url, **kwargs):
            return FakeResponse()

    monkeypatch.setattr("src.services.agent.sandbox_tools.httpx.Client", FakeClient)

    result = execute_request("GET", "/health")
    assert result["status_code"] == 200
    assert result["truncated"] is True
    assert "notice" in result
    assert len(result["body"]) == MAX_RESPONSE_CHARS


def test_execute_request_rejects_invalid_method():
    with pytest.raises(ValueError, match="Unsupported method"):
        execute_request("TRACE", "/health")


def test_execute_request_rejects_invalid_endpoint_prefix():
    with pytest.raises(ValueError, match="blocked"):
        execute_request("GET", "/agent/chat")


def test_discover_api_injects_runtime_branch_and_revision():
    def fake_spec() -> dict:
        return {
            "graphql": {
                "examples": {
                    "ifc_queries": {
                        "ifc_products_count": {
                            "variables": {
                                "branchId": "CURRENT_BRANCH_ID",
                                "revision": None,
                            }
                        }
                    }
                }
            }
        }

    result = discover_api(
        fake_spec,
        branch_id="8f8bb275-7f74-4e0f-b9d8-e63812345678",
        revision=7,
    )
    variables = result["graphql"]["examples"]["ifc_queries"]["ifc_products_count"]["variables"]
    assert variables["branchId"] == "8f8bb275-7f74-4e0f-b9d8-e63812345678"
    assert variables["revision"] == 7
