#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load .env if present
if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

DB_HOST="${BIMATLAS_DB_HOST:-localhost}"
DB_PORT="${BIMATLAS_DB_PORT:-5432}"

# Pre-flight: check if database is reachable
if ! command -v nc &>/dev/null; then
  # nc not available, skip check
  :
elif ! nc -z -w 2 "$DB_HOST" "$DB_PORT" 2>/dev/null; then
  echo "Error: Cannot connect to database at $DB_HOST:$DB_PORT"
  echo "Start PostgreSQL first:"
  echo "  cd infra && docker compose up -d"
  echo "Then wait a few seconds and try again."
  exit 1
fi

exec uvicorn src.main:app --reload --port "${PORT:-8000}"
