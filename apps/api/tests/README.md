# BimAtlas Backend Tests

Unit tests for the BimAtlas API using pytest and a dedicated test database.

## Quick Start

```bash
cd apps/api
./setup_test_db.sh
uv pip install -e ".[dev]"
pytest
```

## Prerequisites

- PostgreSQL with Apache AGE extension
- Python 3.11+
- Docker (for database via `infra/docker-compose.yml`)

## Test Structure

```
tests/
├── conftest.py          # Shared fixtures
├── test_geometry.py     # IFC geometry extraction
├── test_ingestion.py    # Ingestion pipeline
├── test_api.py          # FastAPI endpoints
└── test_db.py           # Database operations
```

## Running Tests

```bash
pytest                                    # All tests
pytest tests/test_api.py                  # Specific file
pytest tests/test_api.py::TestHealthEndpoint::test_health_check  # Specific test
pytest --cov=src --cov-report=term-missing   # With coverage
pytest -n auto                             # Parallel (requires pytest-xdist)
```

## Cleanup

| Command | Purpose |
|---------|---------|
| `pytest` | Auto-cleanup after tests (default) |
| `pytest --no-teardown` | Keep data for inspection |
| `./cleanup_test_db.sh` | Manual cleanup between runs |
| `./teardown_test_db.sh` | Remove test database (run `./setup_test_db.sh` after) |

After `--no-teardown`, inspect with `docker exec -it age_postgres psql -U bimatlas -d bimatlas_test`, then run `./cleanup_test_db.sh` when done.

## Configuration

Environment variables (defaults apply if using docker-compose):

```bash
TEST_DB_HOST=localhost
TEST_DB_PORT=5432
TEST_DB_NAME=bimatlas_test
TEST_DB_USER=bimatlas
TEST_DB_PASSWORD=bimatlas
```

## Fixtures

- `clean_db` — Clean database before each test (use for tests that modify data)
- `test_db_connection`, `db_pool`, `age_graph` — Database connections
- `test_ifc_file`, `temp_ifc_file` — Sample IFC files
- `client` — FastAPI test client

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Connection refused | Start PostgreSQL: `cd infra && docker compose up -d` |
| Database not found | Run `./setup_test_db.sh` |
| Module not found | Run `uv pip install -e ".[dev]"` |
| AGE extension errors | `docker exec age_postgres psql -U bimatlas -d bimatlas_test -c "CREATE EXTENSION IF NOT EXISTS age;"` |
| Dirty data between runs | Run `./cleanup_test_db.sh` |

## Debugging

```bash
pytest -vv -s                                    # Verbose, show prints
pytest --pdb                                     # Drop into debugger on failure
pytest tests/test_api.py::TestName::test_method -x  # Stop at first failure
```
