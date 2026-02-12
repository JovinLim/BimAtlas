#!/bin/bash
# Clean up test database without removing it
# This script clears all data but keeps the database structure intact

set -e

echo "=================================="
echo "BimAtlas Test Database Cleanup"
echo "=================================="
echo ""

# Configuration
DB_CONTAINER="age_postgres"
TEST_DB_NAME="bimatlas_test"
TEST_DB_USER="bimatlas"
# Use bimatlas (not postgres) - docker-compose sets POSTGRES_USER=bimatlas
POSTGRES_SUPERUSER="bimatlas"

# Check if PostgreSQL container is running
echo "🔍 Checking if PostgreSQL container is running..."
if ! docker ps | grep -q "$DB_CONTAINER"; then
    echo "❌ ERROR: PostgreSQL container '$DB_CONTAINER' is not running"
    echo "   Start it with: cd infra && docker compose up -d"
    exit 1
fi
echo "✅ PostgreSQL container is running"
echo ""

# Check if database exists
echo "🔍 Checking if test database exists..."
DB_EXISTS=$(docker exec "$DB_CONTAINER" psql -U "$POSTGRES_SUPERUSER" -tAc "SELECT 1 FROM pg_database WHERE datname='$TEST_DB_NAME';")
if [ "$DB_EXISTS" != "1" ]; then
    echo "⚠️  Test database '$TEST_DB_NAME' does not exist"
    echo "   Run ./setup_test_db.sh to create it"
    exit 0
fi
echo "✅ Test database exists"
echo ""

# Clear test graph
echo "🧹 Clearing test graph..."
docker exec "$DB_CONTAINER" psql -U "$TEST_DB_USER" -d "$TEST_DB_NAME" -c "
    LOAD 'age';
    SET search_path = ag_catalog, \"\$user\", public;
    SELECT * FROM cypher('bimatlas_test', \$\$MATCH (n) DETACH DELETE n\$\$) as (result agtype);
" 2>/dev/null || echo "  ℹ️  Graph already empty or doesn't exist"
echo "✅ Test graph cleared"
echo ""

# Truncate tables
echo "🧹 Truncating test tables..."
docker exec "$DB_CONTAINER" psql -U "$TEST_DB_USER" -d "$TEST_DB_NAME" -c "
    TRUNCATE TABLE ifc_products, revisions RESTART IDENTITY CASCADE;
"
echo "✅ Test tables truncated"
echo ""

# Verify cleanup
echo "🔍 Verifying cleanup..."
REVISION_COUNT=$(docker exec "$DB_CONTAINER" psql -U "$TEST_DB_USER" -d "$TEST_DB_NAME" -tAc "SELECT COUNT(*) FROM revisions;")
PRODUCT_COUNT=$(docker exec "$DB_CONTAINER" psql -U "$TEST_DB_USER" -d "$TEST_DB_NAME" -tAc "SELECT COUNT(*) FROM ifc_products;")

echo "  Revisions: $REVISION_COUNT (should be 0)"
echo "  Products: $PRODUCT_COUNT (should be 0)"
echo ""

if [ "$REVISION_COUNT" = "0" ] && [ "$PRODUCT_COUNT" = "0" ]; then
    echo "=================================="
    echo "✅ Cleanup Complete!"
    echo "=================================="
    echo ""
    echo "Test database has been cleaned."
    echo "All data removed, structure intact."
    echo ""
else
    echo "=================================="
    echo "⚠️  Cleanup May Be Incomplete"
    echo "=================================="
    echo ""
    echo "Some data may still remain."
    echo "Consider running ./teardown_test_db.sh to completely remove the database."
    echo ""
fi
