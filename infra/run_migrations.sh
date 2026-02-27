#!/usr/bin/env bash
# Run all SQL migrations in infra/migrations/ in filename order.
# Uses psql if available, otherwise runs via docker compose exec (age-db container).

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MIGRATIONS_DIR="${SCRIPT_DIR}/migrations"
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.yml"
DB_HOST="${BIMATLAS_DB_HOST:-localhost}"
DB_PORT="${BIMATLAS_DB_PORT:-5432}"
DB_NAME="${BIMATLAS_DB_NAME:-bimatlas}"
DB_USER="${BIMATLAS_DB_USER:-bimatlas}"
DB_PASSWORD="${BIMATLAS_DB_PASSWORD:-bimatlas}"

if [[ ! -d "${MIGRATIONS_DIR}" ]]; then
  echo "Migrations directory not found: ${MIGRATIONS_DIR}"
  exit 1
fi

shopt -s nullglob
migrations=("${MIGRATIONS_DIR}"/*.sql)
shopt -u nullglob

if [[ ${#migrations[@]} -eq 0 ]]; then
  echo "No migrations found in ${MIGRATIONS_DIR}"
  exit 0
fi

run_psql() {
  local f="$1"
  if command -v psql &>/dev/null; then
    export PGPASSWORD="${DB_PASSWORD}"
    psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" -v ON_ERROR_STOP=1 -f "$f"
  elif [[ -f "${COMPOSE_FILE}" ]]; then
    docker compose -f "${COMPOSE_FILE}" exec -T age-db psql -U "${DB_USER}" -d "${DB_NAME}" -v ON_ERROR_STOP=1 -f - < "$f"
  else
    echo "psql not found. Install psql or run from infra: cd infra && docker compose up -d && ./run_migrations.sh"
    exit 1
  fi
}

echo "Running ${#migrations[@]} migration(s)..."
for f in "${migrations[@]}"; do
  name="$(basename "$f")"
  echo "  → $name"
  run_psql "$f"
done

echo "Done."
