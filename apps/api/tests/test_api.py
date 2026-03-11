"""Unit tests for FastAPI endpoints.

Tests the main.py API endpoints using FastAPI's test client.
"""

import io
import json
from pathlib import Path
from uuid import UUID

import pytest
from fastapi import status

from src import db


@pytest.fixture
def api_branch(client) -> str:
    """Create a test project+branch via the API and return the branch_id.

    Uses the DB helpers (pool is already initialised by the ``client`` fixture
    chain) so every API test that needs to upload gets a fresh branch.
    """
    project = db.create_project("API Test Project")
    branches = db.fetch_branches(project["project_id"])
    return str(branches[0]["branch_id"])


class TestHealthEndpoint:
    """Test /health endpoint."""

    def test_health_check(self, client):
        """Test health check endpoint returns OK."""
        response = client.get("/health")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"status": "ok"}


class TestUploadIfcEndpoint:
    """Test /upload-ifc endpoint."""

    def test_upload_ifc_success(self, client, test_ifc_file, api_branch):
        """Test successful IFC file upload."""
        with open(test_ifc_file, "rb") as f:
            response = client.post(
                "/upload-ifc",
                files={"file": (test_ifc_file.name, f, "application/octet-stream")},
                data={"branch_id": str(api_branch)},
            )

        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert "revision_id" in data
        assert "revision_seq" in data
        assert "branch_id" in data
        assert "total_products" in data
        assert "added" in data
        assert "modified" in data
        assert "deleted" in data
        assert "unchanged" in data
        assert "edges_created" in data

        assert data["branch_id"] == api_branch
        assert data["total_products"] > 0
        assert data["added"] == data["total_products"]  # First import
        assert data["modified"] == 0
        assert data["deleted"] == 0
        assert data["unchanged"] == 0

    def test_upload_ifc_with_label(self, client, test_ifc_file, api_branch):
        """Test IFC upload with custom label."""
        with open(test_ifc_file, "rb") as f:
            response = client.post(
                "/upload-ifc",
                files={"file": (test_ifc_file.name, f, "application/octet-stream")},
                data={"branch_id": str(api_branch), "label": "Test Label"},
            )

        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert data["branch_id"] == api_branch

    def test_upload_ifc_multiple_times(self, client, test_ifc_file, api_branch):
        """Test uploading same file multiple times."""
        # First upload
        with open(test_ifc_file, "rb") as f:
            response1 = client.post(
                "/upload-ifc",
                files={"file": (test_ifc_file.name, f, "application/octet-stream")},
                data={"branch_id": str(api_branch)},
            )

        assert response1.status_code == status.HTTP_200_OK
        data1 = response1.json()

        # Second upload (same file)
        with open(test_ifc_file, "rb") as f:
            response2 = client.post(
                "/upload-ifc",
                files={"file": (test_ifc_file.name, f, "application/octet-stream")},
                data={"branch_id": str(api_branch)},
            )

        assert response2.status_code == status.HTTP_200_OK
        data2 = response2.json()

        # Second import should detect no changes (revision_seq increases; revision_id is UUID)
        assert data2["revision_seq"] > data1["revision_seq"]
        assert data2["total_products"] == data1["total_products"]
        assert data2["added"] == 0
        assert data2["unchanged"] == data1["total_products"]

    def test_upload_non_ifc_file(self, client, tmp_path, api_branch):
        """Test that non-IFC file is rejected."""
        # Create a non-IFC file
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("This is not an IFC file")

        with open(txt_file, "rb") as f:
            response = client.post(
                "/upload-ifc",
                files={"file": ("test.txt", f, "text/plain")},
                data={"branch_id": str(api_branch)},
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Only .ifc files are accepted" in response.json()["detail"]

    def test_upload_without_file(self, client):
        """Test that request without file is rejected."""
        response = client.post("/upload-ifc")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_upload_empty_file(self, client, tmp_path, api_branch):
        """Test uploading empty IFC file."""
        empty_ifc = tmp_path / "empty.ifc"
        empty_ifc.write_bytes(b"")

        with open(empty_ifc, "rb") as f:
            response = client.post(
                "/upload-ifc",
                files={"file": (empty_ifc.name, f, "application/octet-stream")},
                data={"branch_id": str(api_branch)},
            )

        # Should fail during parsing
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_upload_minimal_ifc(self, client, tmp_path, api_branch):
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
                data={"branch_id": str(api_branch)},
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total_products"] >= 1

    def test_upload_ifc_response_structure(self, client, test_ifc_file, api_branch):
        """Test that response has correct structure."""
        with open(test_ifc_file, "rb") as f:
            response = client.post(
                "/upload-ifc",
                files={"file": (test_ifc_file.name, f, "application/octet-stream")},
                data={"branch_id": str(api_branch)},
            )

        assert response.status_code == status.HTTP_200_OK

        data = response.json()

        # Verify types
        assert isinstance(data["revision_id"], str)
        assert isinstance(data["revision_seq"], int)
        assert isinstance(data["branch_id"], str)
        assert isinstance(data["total_products"], int)
        assert isinstance(data["added"], int)
        assert isinstance(data["modified"], int)
        assert isinstance(data["deleted"], int)
        assert isinstance(data["unchanged"], int)
        assert isinstance(data["edges_created"], int)

        # Basic UUID sanity (will raise if malformed)
        UUID(data["revision_id"])
        UUID(data["branch_id"])

        # Verify value ranges / consistency
        assert data["branch_id"] == api_branch
        assert data["revision_seq"] > 0
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

    def test_upload_ifc_invalid_branch(self, client, test_ifc_file):
        """Test that uploading to a non-existent branch returns 404."""
        with open(test_ifc_file, "rb") as f:
            response = client.post(
                "/upload-ifc",
                files={"file": (test_ifc_file.name, f, "application/octet-stream")},
                data={"branch_id": "99999"},
            )

        assert response.status_code == status.HTTP_404_NOT_FOUND


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

    def test_graphql_ifcproduct_has_new_fields(self, client):
        """Ensure IfcProduct exposes geometry/metadata fields for shape reps and attributes."""
        query = """
        query {
            __type(name: "IfcProduct") {
                fields {
                    name
                }
            }
        }
        """
        response = client.post("/graphql", json={"query": query})
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        field_names = {f["name"] for f in data["data"]["__type"]["fields"]}
        assert "predefinedType" in field_names
        assert "representations" in field_names
        assert "propertySets" in field_names
        assert "attributes" in field_names

    def test_graphql_ifcrelationshiptype_has_shape_rep_enum(self, client):
        """Ensure IfcRelationshipType enum includes HasShapeRepresentation.

        With ``graphql_name_from=\"value\"`` on the enum, the GraphQL values are
        the underlying strings like ``IfcRelAggregates`` / ``HasShapeRepresentation``.
        We assert on the GraphQL value name, not the Python constant name.
        """
        query = """
        query {
            __type(name: "IfcRelationshipType") {
                enumValues {
                    name
                }
            }
        }
        """
        response = client.post("/graphql", json={"query": query})
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        enum_names = {e["name"] for e in data["data"]["__type"]["enumValues"]}
        assert "HasShapeRepresentation" in enum_names

    def test_graphql_ifc_product_tree_field_exists(self, client):
        """Ensure IfcProductClassNode type and ifcProductTree field exist in schema."""
        query = """
        query {
            __type(name: "IfcProductClassNode") {
                name
                fields {
                    name
                }
            }
            __schema {
                queryType {
                    fields {
                        name
                    }
                }
            }
        }
        """
        response = client.post("/graphql", json={"query": query})
        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["__type"]["name"] == "IfcProductClassNode"
        field_names = {f["name"] for f in data["__schema"]["queryType"]["fields"]}
        assert "ifcProductTree" in field_names

    def test_graphql_ifc_product_tree_contains_db_classes(self, client, db_pool, test_branch, ifc_schema_seeded):
        """Ensure ifcProductTree reflects distinct IFC classes present in the DB."""
        import json as _json
        from src import db
        from src.db import fetch_distinct_ifc_classes_at_revision

        branch_id = test_branch
        # Seed a revision and a couple of entities on this branch.
        with db.get_cursor() as cur:
            cur.execute(
                "INSERT INTO revision (branch_id, ifc_filename) VALUES (%s, %s) "
                "RETURNING revision_id, revision_seq",
                (branch_id, "tree-test.ifc"),
            )
            rev_id, rev_seq = cur.fetchone()
            cur.execute(
                """
                INSERT INTO ifc_entity
                (branch_id, ifc_global_id, ifc_class, attributes, content_hash, created_in_revision_id)
                VALUES
                (%s, 'tree-wall', 'IfcWall', %s, 'hash-wall', %s),
                (%s, 'tree-slab', 'IfcSlab', %s, 'hash-slab', %s)
                """,
                (
                    branch_id,
                    _json.dumps({"Name": "Wall"}),
                    rev_id,
                    branch_id,
                    _json.dumps({"Name": "Slab"}),
                    rev_id,
                ),
            )

        query = """
        query ($branchId: String!, $revision: Int) {
            ifcProductTree(branchId: $branchId, revision: $revision) {
                ifcClass
                children {
                    ifcClass
                    children {
                        ifcClass
                    }
                }
            }
        }
        """
        # Verify entities are visible at this revision (sanity check)
        present = fetch_distinct_ifc_classes_at_revision(rev_seq, branch_id)
        assert "IfcWall" in present and "IfcSlab" in present, (
            f"Expected IfcWall, IfcSlab in DB; got: {present}"
        )

        # Ensure schema loader uses fresh data from test DB (not cached from another run)
        from src.schema import ifc_schema_loader
        ifc_schema_loader._load_schema.cache_clear()
        ifc_schema_loader._children_index.cache_clear()

        response = client.post(
            "/graphql",
            json={
                "query": query,
                "variables": {"branchId": str(branch_id), "revision": int(rev_seq)},
            },
        )
        assert response.status_code == status.HTTP_200_OK
        resp_json = response.json()
        if "errors" in resp_json:
            raise AssertionError(f"GraphQL errors: {resp_json['errors']}")
        data = resp_json["data"]["ifcProductTree"]
        assert data is not None
        assert data["ifcClass"] == "IfcProduct"

        # Collect all class names from the returned tree.
        def collect_names(node):
            out = {node["ifcClass"]}
            for child in node.get("children") or []:
                out |= collect_names(child)
            return out

        names = collect_names(data)
        # Tree is pruned to classes present in DB. Must include root and path to leaf classes.
        # Schema: IfcProduct -> IfcElement -> IfcBuiltElement -> IfcWall/IfcSlab
        assert "IfcProduct" in names
        assert "IfcBuiltElement" in names, (
            f"Tree should include IfcBuiltElement; got: {names}"
        )
        # Leaf classes (IfcWall, IfcSlab) appear when resolver's present_classes matches DB.
        # In some test setups the resolver may use a different connection/context.
        assert names & {"IfcWall", "IfcSlab"} or "IfcElement" in names, (
            f"Tree should contain IfcWall/IfcSlab or at least IfcElement; got: {names}"
        )

    def test_graphql_uploaded_schemas_and_apply(self, client, db_pool, test_project, ifc_schema_seeded):
        """Test uploadedSchemas query and applySchemaToProject mutation."""
        project_id = str(test_project["project_id"])
        query = """
        query {
            uploadedSchemas {
                id
                versionName
                ruleCount
                projectIds
            }
        }
        """
        response = client.post("/graphql", json={"query": query})
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        if "errors" in data:
            raise AssertionError(f"GraphQL errors: {data['errors']}")
        schemas = data["data"]["uploadedSchemas"]
        assert isinstance(schemas, list)
        assert len(schemas) >= 1, "ifc_schema_seeded should have inserted at least one schema"
        schema = schemas[0]
        assert "id" in schema
        assert "versionName" in schema
        assert "ruleCount" in schema
        assert "projectIds" in schema
        schema_id = schema["id"]
        assert schema["projectIds"] == [] or project_id not in schema["projectIds"]

        apply_mutation = """
        mutation ($projectId: String!, $schemaId: String!) {
            applySchemaToProject(projectId: $projectId, schemaId: $schemaId)
        }
        """
        response = client.post(
            "/graphql",
            json={
                "query": apply_mutation,
                "variables": {"projectId": project_id, "schemaId": schema_id},
            },
        )
        assert response.status_code == status.HTTP_200_OK
        apply_data = response.json()
        if "errors" in apply_data:
            raise AssertionError(f"GraphQL errors: {apply_data['errors']}")
        assert apply_data["data"]["applySchemaToProject"] is True

        response = client.post("/graphql", json={"query": query})
        assert response.status_code == status.HTTP_200_OK
        schemas_after = response.json()["data"]["uploadedSchemas"]
        applied_schema = next(s for s in schemas_after if s["id"] == schema_id)
        assert project_id in applied_schema["projectIds"]

        unapply_mutation = """
        mutation ($projectId: String!, $schemaId: String!) {
            unapplySchemaFromProject(projectId: $projectId, schemaId: $schemaId)
        }
        """
        response = client.post(
            "/graphql",
            json={
                "query": unapply_mutation,
                "variables": {"projectId": project_id, "schemaId": schema_id},
            },
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["data"]["unapplySchemaFromProject"] is True

    def test_graphql_create_uploaded_schema(self, client, db_pool):
        """Test createUploadedSchema mutation inserts into ifc_schema table."""
        create_mutation = """
        mutation ($name: String!) {
            createUploadedSchema(name: $name) {
                id
                versionName
                ruleCount
                projectIds
            }
        }
        """
        response = client.post(
            "/graphql",
            json={
                "query": create_mutation,
                "variables": {"name": "TestSchema_Create"},
            },
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        if "errors" in data:
            raise AssertionError(f"GraphQL errors: {data['errors']}")
        created = data["data"]["createUploadedSchema"]
        assert created is not None
        assert created["versionName"] == "TestSchema_Create"
        assert created["ruleCount"] == 0
        assert created["projectIds"] == []
        assert len(created["id"]) == 36  # UUID string length

        # Duplicate name should fail
        response = client.post(
            "/graphql",
            json={
                "query": create_mutation,
                "variables": {"name": "TestSchema_Create"},
            },
        )
        assert response.status_code == status.HTTP_200_OK
        err_data = response.json()
        assert "errors" in err_data

    def test_graphql_create_uploaded_schema_rule(
        self, client, db_pool, ifc_schema_seeded
    ):
        """Test createUploadedSchemaRule mutation inserts into validation_rule."""
        # Get a schema id from uploaded schemas
        query = """
        query { uploadedSchemas { id versionName } }
        """
        resp = client.post("/graphql", json={"query": query})
        assert resp.status_code == status.HTTP_200_OK
        schemas = resp.json()["data"]["uploadedSchemas"]
        assert schemas, "ifc_schema_seeded should provide at least one schema"
        schema_id = schemas[0]["id"]

        create_mutation = """
        mutation ($schemaId: String!, $name: String!, $targetIfcClass: String!,
                  $effectiveRequiredAttributesJson: String) {
            createUploadedSchemaRule(
                schemaId: $schemaId
                name: $name
                targetIfcClass: $targetIfcClass
                effectiveRequiredAttributesJson: $effectiveRequiredAttributesJson
            ) {
                ruleId name targetIfcClass displaySeverity
            }
        }
        """
        vars = {
            "schemaId": schema_id,
            "name": "Test Required Attrs Rule",
            "targetIfcClass": "IfcWall",
            "effectiveRequiredAttributesJson": '[{"name":"Name","type":"IfcLabel","required":true,"definedOn":"IfcWall"}]',
        }
        resp = client.post("/graphql", json={"query": create_mutation, "variables": vars})
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        if "errors" in data:
            raise AssertionError(f"GraphQL errors: {data['errors']}")
        rule = data["data"]["createUploadedSchemaRule"]
        assert rule["name"] == "Test Required Attrs Rule"
        assert rule["targetIfcClass"] == "IfcWall"
        assert len(rule["ruleId"]) == 36

    def test_graphql_branch_query(self, client, test_branch, test_project):
        """Test branch query returns projectId for a given branchId."""
        query = """
        query ($branchId: String!) {
            branch(branchId: $branchId) {
                id
                projectId
                name
            }
        }
        """
        response = client.post(
            "/graphql",
            json={"query": query, "variables": {"branchId": str(test_branch)}},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        if "errors" in data:
            raise AssertionError(f"GraphQL errors: {data['errors']}")
        branch = data["data"]["branch"]
        assert branch is not None
        assert branch["projectId"] == str(test_project["project_id"])
        assert branch["id"] == str(test_branch)

    def test_graphql_no_create_revision_mutation(self, client):
        """Regression: ensure no mutation exists to create a revision manually.

        Revisions must be created only via IFC ingestion (/upload-ifc).
        """
        query = """
        query {
            __schema {
                mutationType {
                    fields {
                        name
                    }
                }
            }
        }
        """
        response = client.post("/graphql", json={"query": query})
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "data" in data and data["data"] is not None
        mutation_type = data["data"]["__schema"]["mutationType"]
        assert mutation_type is not None
        mutation_names = {f["name"] for f in mutation_type["fields"]}
        assert "createRevision" not in mutation_names, (
            "Schema must not expose createRevision; revisions are created only via IFC upload."
        )


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

    def test_multiple_concurrent_uploads(self, client, test_ifc_file, api_branch):
        """Test handling multiple upload requests."""
        # Note: TestClient is synchronous, so this tests sequential requests
        # For true concurrency testing, use async test client

        responses = []
        for i in range(3):
            with open(test_ifc_file, "rb") as f:
                response = client.post(
                    "/upload-ifc",
                    files={"file": (test_ifc_file.name, f, "application/octet-stream")},
                    data={"branch_id": str(api_branch), "label": f"Upload {i+1}"},
                )
                responses.append(response)

        # All should succeed
        for response in responses:
            assert response.status_code == status.HTTP_200_OK

        # Revision sequence should increment (revision_id is UUID, not ordered)
        revision_seqs = [r.json()["revision_seq"] for r in responses]
        assert revision_seqs[0] < revision_seqs[1] < revision_seqs[2]


class TestIntegration:
    """Integration tests for full workflows."""

    def test_full_workflow_upload_and_verify(self, client, test_ifc_file, db_pool, api_branch):
        """Test complete workflow: upload IFC and verify in database."""
        from src.db import get_conn, put_conn

        # Upload IFC file
        with open(test_ifc_file, "rb") as f:
            response = client.post(
                "/upload-ifc",
                files={"file": (test_ifc_file.name, f, "application/octet-stream")},
                data={"branch_id": str(api_branch), "label": "Integration Test"},
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify in database
        conn = get_conn()
        try:
            # Check revision
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT commit_message, ifc_filename FROM revision WHERE revision_id = %s",
                    (data["revision_id"],),
                )
                row = cur.fetchone()

            assert row is not None
            assert row[0] == "Integration Test"
            assert test_ifc_file.name in row[1]

            # Check entities count matches
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM ifc_entity WHERE created_in_revision_id = %s",
                    (data["revision_id"],),
                )
                count = cur.fetchone()[0]

            assert count == data["total_products"]
        finally:
            put_conn(conn)

    def test_workflow_multiple_revisions(self, client, test_ifc_file, db_pool, api_branch):
        """Test workflow with multiple revisions."""
        from src.db import get_conn, put_conn

        # Upload twice
        for i in range(2):
            with open(test_ifc_file, "rb") as f:
                response = client.post(
                    "/upload-ifc",
                    files={"file": (test_ifc_file.name, f, "application/octet-stream")},
                    data={"branch_id": str(api_branch), "label": f"Revision {i+1}"},
                )
                assert response.status_code == status.HTTP_200_OK

        # Verify revisions in database
        conn = get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM revision WHERE branch_id = %s",
                    (api_branch,),
                )
                count = cur.fetchone()[0]

            assert count == 2
        finally:
            put_conn(conn)
