#!/bin/bash
# Teardown test database for BimAtlas backend tests
# This script completely removes the test database and all its data

set -e

echo "=================================="
echo "BimAtlas Test Database Teardown"
echo "=================================="
echo ""

# Configuration
DB_CONTAINER="age_postgres"
TEST_DB_NAME="bimatlas_test"
POSTGRES_SUPERUSER="bimatlas"  # Superuser from docker-compose.yml

# Check if PostgreSQL container is running
echo "🔍 Checking if PostgreSQL container is running..."
if ! docker ps | grep -q "$DB_CONTAINER"; then
    echo "⚠️  PostgreSQL container '$DB_CONTAINER' is not running"
    echo "   Nothing to tear down."
    exit 0
fi
echo "✅ PostgreSQL container is running"
echo ""

# Ask for confirmation
echo "⚠️  WARNING: This will completely delete the test database '$TEST_DB_NAME'"
echo "   All test data will be permanently lost."
echo ""
read -p "Are you sure you want to continue? (yes/no): " -r
echo ""

if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    echo "❌ Teardown cancelled"
    exit 1
fi

# Drop test graph (if it exists)
echo "🗑️  Dropping test graph..."
docker exec "$DB_CONTAINER" psql -U bimatlas -d "$TEST_DB_NAME" -c "LOAD 'age'; SET search_path = ag_catalog, \"\$user\", public; SELECT drop_graph('bimatlas_test', true);" 2>/dev/null || echo "  ℹ️  Graph already removed or doesn't exist"
echo ""

# Drop test database
echo "🗑️  Dropping test database '$TEST_DB_NAME'..."
docker exec "$DB_CONTAINER" psql -U "$POSTGRES_SUPERUSER" -c "DROP DATABASE IF EXISTS $TEST_DB_NAME;" 2>/dev/null
echo "✅ Test database dropped"
echo ""

echo "=================================="
echo "✅ Teardown Complete!"
echo "=================================="
echo ""
echo "The test database has been completely removed."
echo ""
echo "To recreate it, run:"
echo "  ./setup_test_db.sh"
echo ""
