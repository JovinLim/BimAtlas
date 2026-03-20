# Testing Guidelines

Testing strategy and conventions for BimAtlas.

## Backend Testing (Python/pytest)

### Test Structure

```
apps/api/tests/
├── conftest.py           # Shared fixtures
├── test_geometry.py      # IFC parsing and geometry extraction
├── test_ingestion.py     # Ingestion pipeline and diff logic
├── test_api.py           # GraphQL API endpoints
├── test_db.py            # Database operations
└── test_<feature>.py     # Feature-specific tests
```

### Running Tests

```bash
cd apps/api
./setup_test_db.sh   # One-time test database setup
./run_tests.sh       # Run all tests
```

### Test Database

- Tests use isolated `bimatlas_test` database
- Setup script creates fresh schema and test fixtures
- Teardown script drops and recreates database

### Best Practices

- Use fixtures for common setup (db connection, test data)
- Mock external services (IfcOpenShell, LLM providers)
- Use descriptive test names: `test_<method>_<expected_behavior>`
- Test both success and error cases
- Keep tests fast and independent

## Frontend Testing (Playwright)

### Table/Spreadsheet Tests

```
apps/web/tests/table-spreadsheet/
```

### Running Playwright Tests

```bash
cd apps/web
pnpm exec playwright install chromium  # One-time browser install
pnpm run test:spreadsheet              # Headless run
pnpm run test:spreadsheet:headed      # Headed mode for debugging
```

### Test Conventions

- Tests use fixture data (no backend required)
- Target `/table?fixture=1` route
- Test isolated UI components and user interactions

## Coverage Goals

- Backend: Focus on critical paths (ingestion, API, validation)
- Frontend: Critical user workflows
- Minimum acceptable coverage: 80%

## CI/CD

- All tests must pass before merging
- Run linting checks: `ruff check` (Python), `pnpm run check` (Svelte)
