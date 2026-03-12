# AGENTS.md

## Cursor Cloud specific instructions

### Architecture Overview

BimAtlas is a monorepo with two apps and infrastructure:

| Service | Location | Port | Purpose |
|---------|----------|------|---------|
| PostgreSQL + Apache AGE | `infra/docker-compose.yml` | 5432 | Database with graph extension |
| FastAPI API | `apps/api/` | 8000 | GraphQL API + IFC upload |
| SvelteKit Frontend | `apps/web/` | 5173 | Web UI (Three.js + 3d-force-graph) |
| Adminer (optional) | via docker compose | 8080 | DB admin UI |

### Starting services

1. **Database:** `cd infra && docker compose up -d` — wait a few seconds for PostgreSQL to initialize.
2. **API:** `cd apps/api && source .venv/bin/activate && uvicorn src.main:app --reload --host 0.0.0.0 --port 8000 --timeout-graceful-shutdown 5`
3. **Frontend:** `cd apps/web && pnpm run dev --host 0.0.0.0`

### Non-obvious caveats

- **Docker-in-Docker:** The cloud VM runs inside a container. Docker requires `fuse-overlayfs` storage driver and `iptables-legacy`. The daemon config (`/etc/docker/daemon.json`) must set `"storage-driver": "fuse-overlayfs"`, and iptables alternatives must be switched to legacy mode. Start dockerd manually: `sudo dockerd &>/tmp/dockerd.log &`.
- **`run.sh` host binding bug:** `apps/api/run.sh` passes `--host $DB_HOST` to uvicorn (line 29), which defaults to `localhost`. This binds the API only to localhost. Use `--host 0.0.0.0` when you need the API accessible from outside (e.g., browser in the VM Desktop pane).
- **Frontend missing `$lib/` components:** The `.gitignore` contains `lib/` (from Python packaging templates) which inadvertently excludes `apps/web/src/lib/` from version control. All SvelteKit `$lib/` components (Viewport, SelectionPanel, ForceGraph, etc.) were never committed. The frontend dev server starts but renders errors on page load. The backend API and GraphQL playground (`http://localhost:8000/graphql`) are fully functional.
- **`psycopg2` build dependency:** `apache-age-python` depends on `psycopg2` (not binary). Building it requires `libpq-dev` and `python3-dev` system packages.
- **`esbuild` build script:** pnpm blocks esbuild's postinstall by default. Add `"pnpm": {"onlyBuiltDependencies": ["esbuild"]}` to `apps/web/package.json` or run `pnpm install` after the first install triggers the esbuild binary download.
- **PATH for `uv`:** After `pip install uv`, the binary lands in `~/.local/bin/`. Ensure `PATH` includes it.
- **Reload hang with SSE:** With `--reload`, uvicorn waits for connections to close before restarting. SSE endpoints (`/stream/agent-events`, `/stream/ifc-products`) keep connections open indefinitely, so without `--timeout-graceful-shutdown` the server would hang until Ctrl+C. `run.sh` sets a 5s timeout (override via `UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN`).

### Running tests

See the workspace rule in `.cursor/rules/python-tests.mdc` for Python test setup. In brief:

```bash
cd apps/api
source .venv/bin/activate
./setup_test_db.sh   # one-time: creates bimatlas_test DB in the Docker container
./run_tests.sh       # runs 127+ pytest tests
```

### Linting

- **Python:** `cd apps/api && source .venv/bin/activate && ruff check .` (ruff is installed via `uv pip install ruff`)
- **Frontend:** `cd apps/web && pnpm run check` (pre-existing type errors exist due to missing `$lib/` components)
