"""Basic setup tests to verify test infrastructure is working."""

import pytest


class TestBasicSetup:
    """Verify basic test infrastructure."""
    
    def test_pytest_works(self):
        """Verify pytest is working."""
        assert True
    
    def test_imports_work(self):
        """Verify imports work."""
        from src import db, config
        from src.main import app
        
        assert db is not None
        assert config is not None
        assert app is not None
    
    def test_test_db_connection(self, test_db_connection):
        """Verify test database connection works."""
        assert test_db_connection is not None
        assert not test_db_connection.closed
    
    def test_clean_db_fixture(self, clean_db):
        """Verify clean_db fixture works."""
        with clean_db.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM revisions")
            count = cur.fetchone()[0]
        
        # Should start with empty tables
        assert count == 0
    
    def test_db_pool_fixture(self, db_pool):
        """Verify db_pool fixture works."""
        from src.db import get_conn, put_conn
        
        conn = get_conn()
        assert conn is not None
        put_conn(conn)
    
    def test_test_ifc_file_exists(self, test_ifc_file):
        """Verify test IFC file exists."""
        assert test_ifc_file.exists()
        assert test_ifc_file.suffix == ".ifc"
        assert test_ifc_file.stat().st_size > 0
