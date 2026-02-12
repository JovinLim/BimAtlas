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
# Database Schema Setup SQL
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
-- Drop existing tables if they exist
DROP TABLE IF EXISTS ifc_products CASCADE;
DROP TABLE IF EXISTS revisions CASCADE;

-- Create revisions table
CREATE TABLE IF NOT EXISTS revisions (
    id SERIAL PRIMARY KEY,
    label TEXT,
    ifc_filename TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create ifc_products table (SCD Type 2)
CREATE TABLE IF NOT EXISTS ifc_products (
    id SERIAL PRIMARY KEY,
    global_id TEXT NOT NULL,
    ifc_class TEXT NOT NULL,
    name TEXT,
    description TEXT,
    object_type TEXT,
    tag TEXT,
    contained_in TEXT,
    vertices BYTEA,
    normals BYTEA,
    faces BYTEA,
    matrix BYTEA,
    content_hash TEXT NOT NULL,
    valid_from_rev INTEGER NOT NULL REFERENCES revisions(id),
    valid_to_rev INTEGER,
    CONSTRAINT ifc_products_validity CHECK (valid_to_rev IS NULL OR valid_to_rev > valid_from_rev)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_ifc_products_global_id ON ifc_products(global_id);
CREATE INDEX IF NOT EXISTS idx_ifc_products_valid_from ON ifc_products(valid_from_rev);
CREATE INDEX IF NOT EXISTS idx_ifc_products_valid_to ON ifc_products(valid_to_rev);
CREATE INDEX IF NOT EXISTS idx_ifc_products_current ON ifc_products(global_id) WHERE valid_to_rev IS NULL;
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
    """
    # Connect to the test database
    conn = psycopg2.connect(**TEST_DB_CONFIG)
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
                    
                    # Truncate tables to leave database clean
                    try:
                        cur.execute("TRUNCATE TABLE ifc_products, revisions RESTART IDENTITY CASCADE;")
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
        # Truncate tables
        cur.execute("TRUNCATE TABLE ifc_products, revisions RESTART IDENTITY CASCADE;")
        
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


# ---------------------------------------------------------------------------
# Test Data Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def test_ifc_file() -> Path:
    """Provide path to the test IFC file."""
    ifc_path = Path(__file__).parent.parent.parent / "tests" / "files" / "Ifc4_SampleHouse.ifc"
    if not ifc_path.exists():
        # Try alternative location
        ifc_path = Path(__file__).parent.parent.parent / "tests" / "Ifc4_SampleHouse.ifc"
    
    if not ifc_path.exists():
        pytest.skip(f"Test IFC file not found at {ifc_path}")
    
    return ifc_path


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
