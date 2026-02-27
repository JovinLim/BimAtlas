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

# Terminate active connections
# This prevents "database is being accessed by other users" errors
echo "🔌 Terminating active connections to '$TEST_DB_NAME'..."
docker exec "$DB_CONTAINER" psql -U "$POSTGRES_SUPERUSER" -d "postgres" -c \
"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$TEST_DB_NAME' AND pid <> pg_backend_pid();" > /dev/null
echo "✅ Connections cleared"

# Reset Apache AGE Graph
# Drop if exists (ignore error when graph doesn't exist), then create
echo "🧹 Recreating Apache AGE graph..."
docker exec "$DB_CONTAINER" psql -U "$POSTGRES_SUPERUSER" -d "$TEST_DB_NAME" -c "
    LOAD 'age';
    SET search_path = ag_catalog, \"\$user\", public;
    DO \$\$
    BEGIN
        PERFORM drop_graph('$TEST_DB_NAME', true);
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'Graph $TEST_DB_NAME does not exist, skipping drop';
    END \$\$;
    SELECT create_graph('$TEST_DB_NAME');
"
echo "✅ Graph reset (metadata and data cleared)"

# Truncate Relational Tables (matches conftest.py schema)
# Order respects FK constraints; CASCADE handles dependent tables
echo "🧹 Truncating relational tables and resetting IDs..."
SCHEMA_EXISTS=$(docker exec "$DB_CONTAINER" psql -U "$POSTGRES_SUPERUSER" -d "$TEST_DB_NAME" -tAc \
    "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='revision';" 2>/dev/null || echo "")

if [ "$SCHEMA_EXISTS" = "1" ]; then
    # Truncate only tables that exist (schema may vary across migrations)
    docker exec "$DB_CONTAINER" psql -U "$POSTGRES_SUPERUSER" -d "$TEST_DB_NAME" -c "
        DO \$\$
        DECLARE
            tbl_list text;
        BEGIN
            SELECT string_agg(quote_ident(tablename), ', ')
            INTO tbl_list
            FROM pg_tables
            WHERE schemaname = 'public'
            AND tablename IN (
                'merge_conflict_log', 'validation_rule', 'merge_request',
                'ifc_entity', 'branch_applied_filter_sets', 'filter_sets',
                'revision', 'branch', 'project_schema', 'project', 'ifc_schema'
            );
            IF tbl_list IS NOT NULL AND tbl_list != '' THEN
                EXECUTE 'TRUNCATE TABLE ' || tbl_list || ' RESTART IDENTITY CASCADE';
            END IF;
        END \$\$;
    " > /dev/null
    echo "✅ Tables truncated & IDs reset"
else
    echo "⚠️  Relational schema not initialized (revision table missing)"
    echo "   Run tests once to create schema, or run ./setup_test_db.sh"
    echo "   Skipping table truncation."
fi

# Verify cleanup (only if schema exists)
echo "🔍 Verifying cleanup..."
if [ "$SCHEMA_EXISTS" = "1" ]; then
    REVISION_COUNT=$(docker exec "$DB_CONTAINER" psql -U "$TEST_DB_USER" -d "$TEST_DB_NAME" -tAc "SELECT COUNT(*) FROM revision;" 2>/dev/null || echo "?")
    ENTITY_COUNT=$(docker exec "$DB_CONTAINER" psql -U "$TEST_DB_USER" -d "$TEST_DB_NAME" -tAc "SELECT COUNT(*) FROM ifc_entity;" 2>/dev/null || echo "?")
    echo "  Revisions: $REVISION_COUNT (should be 0)"
    echo "  Entities: $ENTITY_COUNT (should be 0)"
else
    REVISION_COUNT="0"
    ENTITY_COUNT="0"
fi
echo ""

if [ "$REVISION_COUNT" = "0" ] && [ "$ENTITY_COUNT" = "0" ]; then
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
