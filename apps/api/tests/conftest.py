"""Pytest configuration and shared fixtures for BimAtlas backend tests.

This module provides fixtures for:
- Test database setup/teardown
- Test IFC file fixtures
- Mock database connections
- FastAPI test client

Cleanup behavior:
- By default, test data is cleaned up after each test session
- Use --no-teardown flag to keep data for inspection after tests
- Use cleanup_test_db.sh to manually clean data between test runs
- Use teardown_test_db.sh to completely remove the test database
"""

import os
import tempfile
from pathlib import Path
from typing import Generator

# CRITICAL: Force test database config BEFORE any app modules load.
# The app reads BIMATLAS_DB_* and BIMATLAS_AGE_GRAPH at import time.
# Without this, tests could run against production/development database.
_test_db_host = os.getenv("TEST_DB_HOST", "localhost")
_test_db_port = os.getenv("TEST_DB_PORT", "5432")
_test_db_name = os.getenv("TEST_DB_NAME", "bimatlas_test")
_test_db_user = os.getenv("TEST_DB_USER", "bimatlas")
_test_db_password = os.getenv("TEST_DB_PASSWORD", "bimatlas")
os.environ["BIMATLAS_DB_HOST"] = _test_db_host
os.environ["BIMATLAS_DB_PORT"] = _test_db_port
os.environ["BIMATLAS_DB_NAME"] = _test_db_name
os.environ["BIMATLAS_DB_USER"] = _test_db_user
os.environ["BIMATLAS_DB_PASSWORD"] = _test_db_password
os.environ["BIMATLAS_AGE_GRAPH"] = "bimatlas_test"

import psycopg2
import psycopg2.pool
import pytest
from fastapi.testclient import TestClient

# Import the app and db modules
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src import db, config
from src.main import app
from src.services.graph import age_client


# ---------------------------------------------------------------------------
# Pytest Command-line Options
# ---------------------------------------------------------------------------

def pytest_addoption(parser):
    """Add custom command-line options for test database management."""
    parser.addoption(
        "--no-teardown",
        action="store_true",
        default=False,
        help="Skip test database teardown after tests (leave data for inspection)",
    )
    parser.addoption(
        "--keep-graph",
        action="store_true",
        default=False,
        help="Keep test graph data after tests (implies --no-teardown for graph only)",
    )


# ---------------------------------------------------------------------------
# Test Database Configuration
# ---------------------------------------------------------------------------

TEST_DB_CONFIG = {
    "host": os.getenv("TEST_DB_HOST", "localhost"),
    "port": int(os.getenv("TEST_DB_PORT", "5432")),
    "dbname": os.getenv("TEST_DB_NAME", "bimatlas_test"),
    "user": os.getenv("TEST_DB_USER", "bimatlas"),
    "password": os.getenv("TEST_DB_PASSWORD", "bimatlas"),  # Same as docker-compose.yml
}


# ---------------------------------------------------------------------------
# Database Schema Setup SQL (matches infra/init-age.sql target schema)
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
-- Drop existing tables (reverse dependency order)
DROP TABLE IF EXISTS merge_conflict_log CASCADE;
DROP TABLE IF EXISTS merge_request CASCADE;
DROP TABLE IF EXISTS validation_rule CASCADE;
DROP TABLE IF EXISTS branch_applied_filter_sets CASCADE;
DROP TABLE IF EXISTS sheet_template CASCADE;
DROP TABLE IF EXISTS filter_sets CASCADE;
DROP TABLE IF EXISTS ifc_entity CASCADE;
DROP TABLE IF EXISTS revision CASCADE;
DROP TABLE IF EXISTS branch CASCADE;
DROP TABLE IF EXISTS project_schema CASCADE;
DROP TABLE IF EXISTS project CASCADE;
DROP TABLE IF EXISTS ifc_schema CASCADE;
DROP TYPE IF EXISTS resolution_status CASCADE;
DROP TYPE IF EXISTS conflict_type CASCADE;
DROP TYPE IF EXISTS merge_status CASCADE;
DROP TYPE IF EXISTS rule_severity CASCADE;
DROP TYPE IF EXISTS logic_operator CASCADE;

CREATE TYPE logic_operator AS ENUM ('AND', 'OR');
CREATE TYPE rule_severity AS ENUM ('Error', 'Warning', 'Info');
CREATE TYPE merge_status AS ENUM ('Draft', 'Previewing', 'Conflict', 'Ready', 'Merged', 'Closed');
CREATE TYPE conflict_type AS ENUM ('Attribute_Mismatch', 'Geometry_Mismatch', 'Topology_Mismatch', 'Deleted_vs_Modified');
CREATE TYPE resolution_status AS ENUM ('Unresolved', 'Source_Wins', 'Target_Wins', 'Manual_Merge');

CREATE TABLE IF NOT EXISTS ifc_schema (
    schema_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version_name VARCHAR NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS project (
    project_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name         VARCHAR NOT NULL,
    description  TEXT,
    created_at   TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS project_schema (
    project_id UUID NOT NULL REFERENCES project(project_id) ON DELETE CASCADE,
    schema_id  UUID NOT NULL REFERENCES ifc_schema(schema_id) ON DELETE CASCADE,
    PRIMARY KEY (project_id, schema_id)
);

CREATE TABLE IF NOT EXISTS branch (
    branch_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id  UUID NOT NULL REFERENCES project(project_id) ON DELETE CASCADE,
    name        VARCHAR NOT NULL DEFAULT 'main',
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT now(),
    UNIQUE (project_id, name)
);
CREATE INDEX IF NOT EXISTS idx_branch_project ON branch(project_id);

CREATE TABLE IF NOT EXISTS revision (
    revision_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    branch_id          UUID NOT NULL REFERENCES branch(branch_id) ON DELETE CASCADE,
    revision_seq       SERIAL NOT NULL,
    parent_revision_id UUID REFERENCES revision(revision_id),
    ifc_filename       TEXT,
    author_id          VARCHAR,
    commit_message     TEXT,
    created_at         TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_revision_branch ON revision(branch_id);
CREATE INDEX IF NOT EXISTS idx_revision_seq ON revision(branch_id, revision_seq);

CREATE TABLE IF NOT EXISTS ifc_entity (
    entity_id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    branch_id                UUID NOT NULL REFERENCES branch(branch_id) ON DELETE CASCADE,
    ifc_global_id            VARCHAR NOT NULL,
    ifc_class                VARCHAR NOT NULL,
    attributes               JSONB NOT NULL DEFAULT '{}',
    geometry                 BYTEA,
    content_hash             TEXT NOT NULL,
    created_in_revision_id   UUID NOT NULL REFERENCES revision(revision_id),
    obsoleted_in_revision_id UUID REFERENCES revision(revision_id),
    UNIQUE (branch_id, ifc_global_id, created_in_revision_id)
);
CREATE INDEX IF NOT EXISTS idx_ifc_entity_current ON ifc_entity(branch_id, ifc_global_id) WHERE obsoleted_in_revision_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_ifc_entity_class ON ifc_entity(branch_id, ifc_class) WHERE obsoleted_in_revision_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_ifc_entity_attributes ON ifc_entity USING GIN (attributes);

CREATE TABLE IF NOT EXISTS filter_sets (
    filter_set_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    branch_id     UUID NOT NULL REFERENCES branch(branch_id) ON DELETE CASCADE,
    name          VARCHAR NOT NULL,
    logic         logic_operator NOT NULL DEFAULT 'AND',
    filters       JSONB NOT NULL DEFAULT '[]',
    color         VARCHAR NOT NULL DEFAULT '#4A90D9',
    created_at    TIMESTAMPTZ DEFAULT now(),
    updated_at    TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_filter_sets_branch ON filter_sets(branch_id);

CREATE TABLE IF NOT EXISTS sheet_template (
    sheet_template_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id        UUID NOT NULL REFERENCES project(project_id) ON DELETE CASCADE,
    name              VARCHAR NOT NULL,
    sheet             JSONB NOT NULL DEFAULT '{}',
    open              BOOLEAN NOT NULL DEFAULT FALSE,
    created_at        TIMESTAMPTZ DEFAULT now(),
    updated_at        TIMESTAMPTZ DEFAULT now(),
    UNIQUE (project_id, name)
);
CREATE INDEX IF NOT EXISTS idx_sheet_template_project ON sheet_template(project_id);

CREATE TABLE IF NOT EXISTS branch_applied_filter_sets (
    branch_id         UUID NOT NULL REFERENCES branch(branch_id) ON DELETE CASCADE,
    filter_set_id     UUID NOT NULL REFERENCES filter_sets(filter_set_id) ON DELETE CASCADE,
    combination_logic logic_operator NOT NULL DEFAULT 'AND',
    display_order     INTEGER NOT NULL DEFAULT 0,
    applied_at        TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (branch_id, filter_set_id)
);

CREATE TABLE IF NOT EXISTS merge_request (
    merge_request_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id       UUID NOT NULL REFERENCES project(project_id) ON DELETE CASCADE,
    source_branch_id UUID NOT NULL REFERENCES branch(branch_id),
    target_branch_id UUID NOT NULL REFERENCES branch(branch_id),
    status           merge_status NOT NULL DEFAULT 'Draft',
    created_by       VARCHAR,
    created_at       TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS merge_conflict_log (
    log_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merge_request_id  UUID NOT NULL REFERENCES merge_request(merge_request_id) ON DELETE CASCADE,
    ifc_global_id     VARCHAR NOT NULL,
    source_entity_id  UUID REFERENCES ifc_entity(entity_id),
    target_entity_id  UUID REFERENCES ifc_entity(entity_id),
    conflict_type     conflict_type NOT NULL,
    resolution_status resolution_status NOT NULL DEFAULT 'Unresolved',
    resolved_entity_id UUID REFERENCES ifc_entity(entity_id)
);

CREATE TABLE IF NOT EXISTS validation_rule (
    rule_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name             VARCHAR NOT NULL,
    description      TEXT,
    schema_id        UUID REFERENCES ifc_schema(schema_id) ON DELETE CASCADE,
    project_id       UUID REFERENCES project(project_id),
    target_ifc_class VARCHAR NOT NULL,
    rule_schema      JSONB NOT NULL,
    severity         rule_severity NOT NULL DEFAULT 'Error',
    is_active        BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS agent_chat (
    chat_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES project(project_id) ON DELETE CASCADE,
    branch_id  UUID NOT NULL REFERENCES branch(branch_id) ON DELETE CASCADE,
    title      VARCHAR NOT NULL DEFAULT 'New chat',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_chat_message (
    message_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id    UUID NOT NULL REFERENCES agent_chat(chat_id) ON DELETE CASCADE,
    role       VARCHAR NOT NULL,
    content    TEXT NOT NULL DEFAULT '',
    tool_calls JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);
"""

GRAPH_SETUP_SQL = """
-- Load AGE extension
CREATE EXTENSION IF NOT EXISTS age;
LOAD 'age';
SET search_path = ag_catalog, "$user", public;

-- Drop graph if exists (ignore errors if doesn't exist)
DO $$
BEGIN
    PERFORM drop_graph('bimatlas_test', true);
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'Graph bimatlas_test does not exist, skipping drop';
END $$;

-- Create graph
SELECT create_graph('bimatlas_test');
"""


# ---------------------------------------------------------------------------
# Session-level Fixtures (Database Setup)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def test_db_connection(request) -> Generator[psycopg2.extensions.connection, None, None]:
    """Create a test database connection for the entire test session.
    
    This fixture:
    1. Connects to the test database
    2. Sets up the schema (tables and AGE graph)
    3. Yields the connection
    4. Cleans up after all tests complete (drops graph, truncates tables)
    
    Cleanup can be controlled with pytest options:
    - Use --no-teardown to skip cleanup (leaves data for inspection)
    - Use --keep-graph to keep graph data only
    
    Skips all tests that depend on it if PostgreSQL is not running.
    """
    try:
        conn = psycopg2.connect(**TEST_DB_CONFIG)
    except psycopg2.OperationalError as e:
        pytest.skip(
            f"PostgreSQL not available at {TEST_DB_CONFIG['host']}:{TEST_DB_CONFIG['port']}. "
            f"Start the test database (e.g. docker-compose up -d) and re-run. Error: {e}"
        )
    conn.autocommit = True
    
    # Get command-line options
    no_teardown = request.config.getoption("--no-teardown")
    keep_graph = request.config.getoption("--keep-graph")
    
    try:
        with conn.cursor() as cur:
            # Set up relational schema
            cur.execute(SCHEMA_SQL)
            
            # Set up AGE graph
            try:
                cur.execute(GRAPH_SETUP_SQL)
            except Exception as e:
                print(f"Warning: Could not set up AGE graph: {e}")
                print("Graph tests may fail. Ensure AGE extension is installed.")
        
        yield conn
        
    finally:
        # Cleanup after all tests complete
        if no_teardown:
            print("\n⚠️  Skipping test database cleanup (--no-teardown flag)")
            print("   Run cleanup_test_db.sh to manually clean up")
        else:
            print("\n🧹 Cleaning up test database...")
            
            try:
                with conn.cursor() as cur:
                    # Drop test graph
                    if not keep_graph:
                        try:
                            cur.execute("SET search_path = ag_catalog, \"$user\", public;")
                            cur.execute("SELECT drop_graph('bimatlas_test', true);")
                            print("  ✅ Dropped test graph")
                        except Exception as e:
                            print(f"  ⚠️  Could not drop graph: {e}")
                    else:
                        print("  ⚠️  Keeping test graph (--keep-graph flag)")
                    
                    # Truncate tables to leave database clean (order: FKs first)
                    try:
                        cur.execute(
                            "TRUNCATE TABLE agent_chat_message, agent_chat, "
                            "merge_conflict_log, validation_rule, merge_request, "
                            "ifc_entity, branch_applied_filter_sets, filter_sets, sheet_template, revision, "
                            "branch, project_schema, project, ifc_schema CASCADE;"
                        )
                        print("  ✅ Truncated test tables")
                    except Exception as e:
                        print(f"  ⚠️  Could not truncate tables: {e}")
            except Exception as e:
                print(f"  ⚠️  Cleanup error: {e}")
        
        conn.close()
        print("  ✅ Closed test database connection")
        
        if no_teardown or keep_graph:
            print("\nℹ️  To manually clean up test data:")
            print("   ./cleanup_test_db.sh      # Clean data, keep structure")
            print("   ./teardown_test_db.sh     # Remove database completely")


@pytest.fixture(scope="function")
def clean_db(test_db_connection) -> Generator[psycopg2.extensions.connection, None, None]:
    """Provide a clean database for each test function.
    
    Truncates all tables and resets the graph before each test.
    """
    conn = test_db_connection
    
    with conn.cursor() as cur:
        # Truncate tables (order matters due to FK constraints)
        cur.execute(
            "TRUNCATE TABLE agent_chat_message, agent_chat, merge_conflict_log, validation_rule, merge_request, "
            "ifc_entity, branch_applied_filter_sets, filter_sets, sheet_template, revision, "
            "branch, project_schema, project, ifc_schema CASCADE;"
        )
        
        # Clear schema loader cache (reads from validation_rule / ifc_schema)
        try:
            from src.schema import ifc_schema_loader as _loader
            _loader._load_schema.cache_clear()
            _loader._children_index.cache_clear()
        except Exception:
            pass
        
        # Clear graph
        try:
            cur.execute("SET search_path = ag_catalog, \"$user\", public;")
            cur.execute(
                "SELECT * FROM cypher('bimatlas_test', $$MATCH (n) DETACH DELETE n$$) as (result agtype);"
            )
        except Exception:
            pass
    
    yield conn


@pytest.fixture(scope="function")
def db_pool(clean_db, monkeypatch) -> Generator[None, None, None]:
    """Mock the global connection pool to use test database.
    
    This fixture patches the config module to use test database configuration.
    """
    # Patch config module with test config
    monkeypatch.setattr(config, "DB_HOST", TEST_DB_CONFIG["host"])
    monkeypatch.setattr(config, "DB_PORT", TEST_DB_CONFIG["port"])
    monkeypatch.setattr(config, "DB_NAME", TEST_DB_CONFIG["dbname"])
    monkeypatch.setattr(config, "DB_USER", TEST_DB_CONFIG["user"])
    monkeypatch.setattr(config, "DB_PASSWORD", TEST_DB_CONFIG["password"])
    
    # Initialize pool with test config
    db.init_pool(minconn=1, maxconn=3)
    
    yield
    
    # Cleanup: close pool
    db.close_pool()


@pytest.fixture(scope="function")
def age_graph(clean_db, monkeypatch):
    """Configure AGE client to use test graph."""
    # Patch the graph name to use test graph
    monkeypatch.setattr(config, "AGE_GRAPH", "bimatlas_test")
    
    # Clear known labels cache so labels are recreated for test graph
    age_client._known_vlabels.clear()
    age_client._known_elabels.clear()
    
    yield
    
    # Cleanup
    age_client._known_vlabels.clear()
    age_client._known_elabels.clear()


@pytest.fixture(scope="function")
def test_project(db_pool) -> dict:
    """Create a test project and return the project dict (project_id, name, etc.)."""
    return db.create_project("Test Project", "Test project for unit tests")


@pytest.fixture(scope="function")
def test_branch(db_pool, test_project) -> str:
    """Create a test project with a 'main' branch and return the branch_id (UUID string).
    
    Most tests need a branch_id to work with. This fixture creates a project
    named 'Test Project' with a default 'main' branch and returns the branch_id.
    """
    branches = db.fetch_branches(test_project["project_id"])
    return str(branches[0]["branch_id"])


# ---------------------------------------------------------------------------
# Test Data Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def test_ifc_file() -> Path:
    """Provide path to the test IFC file (Ifc4_SampleHouse.ifc)."""
    # Search order: api tests/files, then apps/test_files (shared), then repo tests
    _base = Path(__file__).resolve().parent  # apps/api/tests
    _apps = _base.parent.parent  # apps
    _root = _apps.parent  # repo root
    candidates = [
        _base / "files" / "Ifc4_SampleHouse.ifc",
        _apps / "test_files" / "Ifc4_SampleHouse.ifc",
        _root / "tests" / "files" / "Ifc4_SampleHouse.ifc",
        _root / "tests" / "Ifc4_SampleHouse.ifc",
        _apps / "tests" / "Ifc4_SampleHouse.ifc",
    ]
    for ifc_path in candidates:
        if ifc_path.exists():
            return ifc_path
    pytest.skip(f"Test IFC file not found. Tried: {[str(p) for p in candidates]}")
    return Path()  # unreachable; skip raises


@pytest.fixture
def ifc_schema_seeded(db_pool) -> None:
    """Seed the IFC4x3 schema into the test DB so ifc_schema_loader and ifcProductTree work."""
    import json as _json
    schema_path = Path(__file__).resolve().parent.parent / "schema" / "ifc_4_3_schema.json"
    if not schema_path.exists():
        pytest.skip(f"Schema file not found: {schema_path}")
    with open(schema_path, encoding="utf-8") as f:
        schema_json = _json.load(f)
    db.insert_validation_rules(
        schema_json.get("schema", "IFC4X3_ADD2"),
        schema_json,
    )


@pytest.fixture
def temp_ifc_file(test_ifc_file) -> Generator[Path, None, None]:
    """Create a temporary copy of the test IFC file."""
    with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as tmp:
        tmp.write(test_ifc_file.read_bytes())
        tmp_path = Path(tmp.name)
    
    yield tmp_path
    
    # Cleanup
    try:
        tmp_path.unlink()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# API Test Client
# ---------------------------------------------------------------------------

@pytest.fixture
def client(db_pool, age_graph) -> TestClient:
    """Provide a FastAPI test client with test database."""
    # The db_pool and age_graph fixtures ensure the app uses test database
    return TestClient(app)


@pytest.fixture
def auth_client(client) -> TestClient:
    """Provide an authenticated test client (if authentication is implemented)."""
    # Placeholder for future authentication
    return client


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

@pytest.fixture
def db_cursor(clean_db):
    """Provide a database cursor for direct DB operations in tests."""
    def _get_cursor():
        return clean_db.cursor()
    
    return _get_cursor
