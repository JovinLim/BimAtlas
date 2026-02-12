#!/bin/bash
# Setup test database for BimAtlas backend tests
# This script creates a separate test database and installs the AGE extension

set -e

echo "=================================="
echo "BimAtlas Test Database Setup"
echo "=================================="
echo ""

# Configuration
DB_CONTAINER="age_postgres"
TEST_DB_NAME="bimatlas_test"
TEST_DB_USER="bimatlas"
TEST_DB_PASS="bimatlas"
POSTGRES_SUPERUSER="bimatlas"  # Superuser from docker-compose.yml

# Check if PostgreSQL container is running
echo "🔍 Checking if PostgreSQL container is running..."
if ! docker ps | grep -q "$DB_CONTAINER"; then
    echo "❌ ERROR: PostgreSQL container '$DB_CONTAINER' is not running"
    echo "   Start it with: cd infra && docker compose up -d"
    exit 1
fi
echo "✅ PostgreSQL container is running"
echo ""

# Create test database
echo "🗄️  Creating test database '$TEST_DB_NAME'..."
docker exec "$DB_CONTAINER" psql -U "$POSTGRES_SUPERUSER" -c "DROP DATABASE IF EXISTS $TEST_DB_NAME;" 2>/dev/null || true
docker exec "$DB_CONTAINER" psql -U "$POSTGRES_SUPERUSER" -c "CREATE DATABASE $TEST_DB_NAME;"
echo "✅ Test database created"
echo ""

# Grant permissions to test user (same user in this case)
echo "🔐 Granting permissions to user '$TEST_DB_USER'..."
docker exec "$DB_CONTAINER" psql -U "$POSTGRES_SUPERUSER" -c "GRANT ALL PRIVILEGES ON DATABASE $TEST_DB_NAME TO $TEST_DB_USER;" 2>/dev/null || echo "  ℹ️  User already has permissions"
echo "✅ Permissions granted"
echo ""

# Install AGE extension
echo "📦 Installing Apache AGE extension..."
docker exec "$DB_CONTAINER" psql -U "$TEST_DB_USER" -d "$TEST_DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS age;"
docker exec "$DB_CONTAINER" psql -U "$TEST_DB_USER" -d "$TEST_DB_NAME" -c "LOAD 'age';"
echo "✅ AGE extension installed"
echo ""

# Verify setup
echo "🧪 Verifying test database setup..."
TEST_RESULT=$(docker exec "$DB_CONTAINER" psql -U "$TEST_DB_USER" -d "$TEST_DB_NAME" -t -c "SELECT 1;" | xargs)
if [ "$TEST_RESULT" = "1" ]; then
    echo "✅ Test database is accessible"
else
    echo "❌ ERROR: Could not connect to test database"
    exit 1
fi
echo ""

# Display connection info
echo "=================================="
echo "✅ Test Database Setup Complete!"
echo "=================================="
echo ""
echo "Connection details:"
echo "  Host:     localhost"
echo "  Port:     5432"
echo "  Database: $TEST_DB_NAME"
echo "  User:     $TEST_DB_USER"
echo "  Password: $TEST_DB_PASS (from docker-compose.yml)"
echo ""
echo "Environment variables:"
echo "  export TEST_DB_HOST=localhost"
echo "  export TEST_DB_PORT=5432"
echo "  export TEST_DB_NAME=$TEST_DB_NAME"
echo "  export TEST_DB_USER=$TEST_DB_USER"
echo "  export TEST_DB_PASSWORD=$TEST_DB_PASS"
echo ""
echo "Run tests with:"
echo "  pytest"
echo ""
