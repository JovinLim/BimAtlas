#!/bin/bash
# Run BimAtlas backend tests
# This script sets up environment and runs pytest

set -e

# Change to API directory
cd "$(dirname "$0")"

echo "=================================="
echo "BimAtlas Backend Tests"
echo "=================================="
echo ""

# Set test environment variables
export TEST_DB_HOST="${TEST_DB_HOST:-localhost}"
export TEST_DB_PORT="${TEST_DB_PORT:-5432}"
export TEST_DB_NAME="${TEST_DB_NAME:-bimatlas_test}"
export TEST_DB_USER="${TEST_DB_USER:-bimatlas}"
export TEST_DB_PASSWORD="${TEST_DB_PASSWORD:-bimatlas}"

# Check if test database exists
echo "🔍 Checking test database..."
if docker exec age_postgres psql -U "$TEST_DB_USER" -d "$TEST_DB_NAME" -c "SELECT 1;" &>/dev/null; then
    echo "✅ Test database is accessible"
else
    echo "⚠️  Test database not found. Setting up..."
    ./setup_test_db.sh
fi
echo ""

# Check if pytest is installed
echo "🔍 Checking pytest installation..."
if ! python -m pytest --version &>/dev/null; then
    echo "❌ ERROR: pytest is not installed"
    echo "   Install with: uv pip install -e '.[dev]'"
    exit 1
fi
echo "✅ pytest is installed"
echo ""

# Parse command line arguments
PYTEST_ARGS=("$@")

# If no arguments provided, use defaults
if [ ${#PYTEST_ARGS[@]} -eq 0 ]; then
    PYTEST_ARGS=("-v")
fi

# Run tests
echo "🧪 Running tests..."
echo "   Command: pytest ${PYTEST_ARGS[*]}"
echo ""
echo "ℹ️  Cleanup options:"
echo "   - Default: Auto-cleanup after tests"
echo "   - Use --no-teardown to skip cleanup (for inspection)"
echo "   - Use --keep-graph to keep graph data only"
echo "   - Run ./cleanup_test_db.sh to manually clean up"
echo ""

python -m pytest "${PYTEST_ARGS[@]}"

# Capture exit code
EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "=================================="
    echo "✅ All tests passed!"
    echo "=================================="
    echo ""
    echo "Test database cleaned automatically."
else
    echo "=================================="
    echo "❌ Some tests failed"
    echo "=================================="
    echo ""
fi

echo "ℹ️  Cleanup commands:"
echo "   ./cleanup_test_db.sh      # Clean data, keep structure"
echo "   ./teardown_test_db.sh     # Remove database completely"
echo ""

exit $EXIT_CODE
