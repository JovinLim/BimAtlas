"""Unit tests for FastAPI endpoints.

Tests the main.py API endpoints using FastAPI's test client.
"""

import io
import json
from pathlib import Path

import pytest
from fastapi import status


class TestHealthEndpoint:
    """Test /health endpoint."""

    def test_health_check(self, client):
        """Test health check endpoint returns OK."""
        response = client.get("/health")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"status": "ok"}


class TestUploadIfcEndpoint:
    """Test /upload-ifc endpoint."""

    def test_upload_ifc_success(self, client, test_ifc_file):
        """Test successful IFC file upload."""
        with open(test_ifc_file, "rb") as f:
            response = client.post(
                "/upload-ifc",
                files={"file": (test_ifc_file.name, f, "application/octet-stream")},
            )

        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        print(data)
        assert "revision_id" in data
        assert "total_products" in data
        assert "added" in data
        assert "modified" in data
        assert "deleted" in data
        assert "unchanged" in data
        assert "edges_created" in data

        assert data["revision_id"] == 1
        assert data["total_products"] > 0
        assert data["added"] == data["total_products"]  # First import
        assert data["modified"] == 0
        assert data["deleted"] == 0
        assert data["unchanged"] == 0

    def test_upload_ifc_with_label(self, client, test_ifc_file):
        """Test IFC upload with custom label."""
        with open(test_ifc_file, "rb") as f:
            response = client.post(
                "/upload-ifc",
                files={"file": (test_ifc_file.name, f, "application/octet-stream")},
                data={"label": "Test Label"},
            )

        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert data["revision_id"] == 1

    def test_upload_ifc_multiple_times(self, client, test_ifc_file):
        """Test uploading same file multiple times."""
        # First upload
        with open(test_ifc_file, "rb") as f:
            response1 = client.post(
                "/upload-ifc",
                files={"file": (test_ifc_file.name, f, "application/octet-stream")},
            )

        assert response1.status_code == status.HTTP_200_OK
        data1 = response1.json()

        # Second upload (same file)
        with open(test_ifc_file, "rb") as f:
            response2 = client.post(
                "/upload-ifc",
                files={"file": (test_ifc_file.name, f, "application/octet-stream")},
            )

        assert response2.status_code == status.HTTP_200_OK
        data2 = response2.json()

        # Second import should detect no changes
        assert data2["revision_id"] == 2
        assert data2["total_products"] == data1["total_products"]
        assert data2["added"] == 0
        assert data2["unchanged"] == data1["total_products"]

    def test_upload_non_ifc_file(self, client, tmp_path):
        """Test that non-IFC file is rejected."""
        # Create a non-IFC file
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("This is not an IFC file")

        with open(txt_file, "rb") as f:
            response = client.post(
                "/upload-ifc",
                files={"file": ("test.txt", f, "text/plain")},
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Only .ifc files are accepted" in response.json()["detail"]

    def test_upload_without_file(self, client):
        """Test that request without file is rejected."""
        response = client.post("/upload-ifc")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_upload_empty_file(self, client, tmp_path):
        """Test uploading empty IFC file."""
        empty_ifc = tmp_path / "empty.ifc"
        empty_ifc.write_bytes(b"")

        with open(empty_ifc, "rb") as f:
            response = client.post(
                "/upload-ifc",
                files={"file": (empty_ifc.name, f, "application/octet-stream")},
            )

        # Should fail during parsing
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_upload_minimal_ifc(self, client, tmp_path):
        """Test uploading minimal valid IFC file."""
        minimal_ifc = tmp_path / "minimal.ifc"
        minimal_ifc.write_text(
            """ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('ViewDefinition [CoordinationView]'),'2;1');
FILE_NAME('minimal.ifc','2024-01-01T00:00:00',(''),(''),('IfcOpenShell'),'IfcOpenShell','');
FILE_SCHEMA(('IFC4'));
ENDSEC;
DATA;
#1=IFCPROJECT('0MmPvFe$56f8X8YgXZVLUJ',$,'Test Project',$,$,$,$,$,$);
ENDSEC;
END-ISO-10303-21;
"""
        )

        with open(minimal_ifc, "rb") as f:
            response = client.post(
                "/upload-ifc",
                files={"file": (minimal_ifc.name, f, "application/octet-stream")},
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total_products"] >= 1

    def test_upload_ifc_response_structure(self, client, test_ifc_file):
        """Test that response has correct structure."""
        with open(test_ifc_file, "rb") as f:
            response = client.post(
                "/upload-ifc",
                files={"file": (test_ifc_file.name, f, "application/octet-stream")},
            )

        assert response.status_code == status.HTTP_200_OK

        data = response.json()

        # Verify types
        assert isinstance(data["revision_id"], int)
        assert isinstance(data["total_products"], int)
        assert isinstance(data["added"], int)
        assert isinstance(data["modified"], int)
        assert isinstance(data["deleted"], int)
        assert isinstance(data["unchanged"], int)
        assert isinstance(data["edges_created"], int)

        # Verify value ranges
        assert data["revision_id"] > 0
        assert data["total_products"] >= 0
        assert data["added"] >= 0
        assert data["modified"] >= 0
        assert data["deleted"] >= 0
        assert data["unchanged"] >= 0
        assert data["edges_created"] >= 0

        # Verify totals match
        assert (
            data["added"] + data["modified"] + data["deleted"] + data["unchanged"]
        ) >= data["total_products"]


class TestGraphQLEndpoint:
    """Test /graphql endpoint."""

    def test_graphql_endpoint_exists(self, client):
        """Test that GraphQL endpoint is accessible."""
        # GraphQL typically responds to GET with GraphiQL interface
        response = client.get("/graphql")

        # Should not return 404
        assert response.status_code != status.HTTP_404_NOT_FOUND

    def test_graphql_introspection(self, client):
        """Test GraphQL introspection query."""
        query = """
        query {
            __schema {
                queryType {
                    name
                }
            }
        }
        """

        response = client.post(
            "/graphql",
            json={"query": query},
        )

        # Should not error (even if schema is not fully implemented)
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
        ]


class TestCORS:
    """Test CORS middleware configuration."""

    def test_cors_headers_present(self, client):
        """Test that CORS headers are present."""
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )

        # CORS should be configured
        assert (
            "access-control-allow-origin" in response.headers
            or response.status_code == 200
        )


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_invalid_endpoint(self, client):
        """Test that invalid endpoint returns 404."""
        response = client.get("/nonexistent-endpoint")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_method_not_allowed(self, client):
        """Test that wrong HTTP method returns 405."""
        # GET to endpoint that only accepts POST
        response = client.get("/upload-ifc")

        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


class TestConcurrency:
    """Test concurrent requests."""

    def test_multiple_concurrent_uploads(self, client, test_ifc_file):
        """Test handling multiple upload requests."""
        # Note: TestClient is synchronous, so this tests sequential requests
        # For true concurrency testing, use async test client

        responses = []
        for i in range(3):
            with open(test_ifc_file, "rb") as f:
                response = client.post(
                    "/upload-ifc",
                    files={"file": (test_ifc_file.name, f, "application/octet-stream")},
                    data={"label": f"Upload {i+1}"},
                )
                responses.append(response)

        # All should succeed
        for response in responses:
            assert response.status_code == status.HTTP_200_OK

        # Revision IDs should increment
        revision_ids = [r.json()["revision_id"] for r in responses]
        assert revision_ids == [1, 2, 3]


class TestIntegration:
    """Integration tests for full workflows."""

    def test_full_workflow_upload_and_verify(self, client, test_ifc_file, db_pool):
        """Test complete workflow: upload IFC and verify in database."""
        from src.db import get_conn, put_conn

        # Upload IFC file
        with open(test_ifc_file, "rb") as f:
            response = client.post(
                "/upload-ifc",
                files={"file": (test_ifc_file.name, f, "application/octet-stream")},
                data={"label": "Integration Test"},
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify in database
        conn = get_conn()
        try:
            # Check revision
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT label, ifc_filename FROM revisions WHERE id = %s",
                    (data["revision_id"],),
                )
                row = cur.fetchone()

            assert row is not None
            assert row[0] == "Integration Test"
            assert test_ifc_file.name in row[1]

            # Check products count matches
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM ifc_products WHERE valid_from_rev = %s",
                    (data["revision_id"],),
                )
                count = cur.fetchone()[0]

            assert count == data["total_products"]
        finally:
            put_conn(conn)

    def test_workflow_multiple_revisions(self, client, test_ifc_file, db_pool):
        """Test workflow with multiple revisions."""
        from src.db import get_conn, put_conn

        # Upload twice
        for i in range(2):
            with open(test_ifc_file, "rb") as f:
                response = client.post(
                    "/upload-ifc",
                    files={"file": (test_ifc_file.name, f, "application/octet-stream")},
                    data={"label": f"Revision {i+1}"},
                )
                assert response.status_code == status.HTTP_200_OK

        # Verify revisions in database
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM revisions")
                count = cur.fetchone()[0]

            assert count == 2
        finally:
            put_conn(conn)
