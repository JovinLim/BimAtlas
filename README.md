# BimAtlas

**Extensible Spatial-Graph Engine for IFC Building Models**

BimAtlas ingests IFC 4.3 files into a versioned PostgreSQL + Apache AGE graph database, exposes them through a GraphQL API, and renders geometry and topology in a SvelteKit frontend powered by Three.js and 3d-force-graph.

Work is organised into **projects** with **branches**. Each branch maintains an independent revision history, enabling parallel design exploration (similar to Git branching).

---

## Architecture

```
SvelteKit 5 (Three.js + 3d-force-graph)
        │  GraphQL
        ▼
FastAPI + Strawberry GraphQL
        │
        ▼
PostgreSQL + Apache AGE
(Relational + Graph in one DB)
```

**Data flow:** Create a project → select a branch → upload IFC file → versioned ingestion (SCD Type 2 diff, scoped per branch) → relational rows + revision-tagged graph nodes/edges → GraphQL resolvers (branch + revision scoped) → frontend decodes Base64 geometry into `THREE.BufferGeometry` and renders the spatial/topological graph.

---

## Monorepo Structure

```
BimAtlas/
  apps/
    web/                        # SvelteKit (Svelte 5, TypeScript)
      src/
        lib/
          engine/               # Three.js scene manager + BufferGeometryLoader
          graph/                # 3d-force-graph integration
          ui/                   # Viewport, SelectionPanel, ImportModal (snippet extensibility)
          state/                # Shared reactive state ($state runes)
          api/                  # GraphQL client
        routes/
      package.json

    api/                        # FastAPI + Strawberry GraphQL
      src/
        main.py                 # App entry, mounts Strawberry router
        config.py               # DB connection settings
        db.py                   # Postgres/AGE connection pool + project/branch/entity queries (JSONB attributes)
        services/
          ifc/
            geometry.py         # IfcOpenShell mesh extraction
            ingestion.py        # Two-phase versioned IFC ingestion (branch-scoped)
          graph/
            age_client.py       # AGE Cypher query builder/executor (branch-scoped)
            queries.py          # Reusable Cypher query templates
        schema/
          ifc_types.py          # IFC 4.3-aligned Strawberry types + Project/Branch types
          ifc_enums.py          # Relationship & element class enums
          mesh_types.py         # MeshData type for geometry blobs
          queries.py            # Root Query + Mutation resolvers
          scalars.py            # Base64 scalar for binary blobs
      pyproject.toml
      requirements.txt
      run.sh                   # Start server (loads .env)

  infra/
    docker-compose.yml          # PostgreSQL/AGE + Adminer (DB web UI on :8080)
    init-age.sql                # Bootstrap: AGE extension + schema (project, branch, revision, ifc_entity, filter_sets, etc.)
    migrations/                 # Incremental SQL migrations (run via run_migrations.sh)
    run_migrations.sh           # Apply migrations in filename order
```

---

## Prerequisites

- **Docker** (for PostgreSQL + Apache AGE)
- **Python 3.11+** with `uv` or `pip`
- **Node.js 20+** with `npm`
- **IfcOpenShell** (installed via pip)

---

## Getting Started

### 1. Start the Database

```bash
cd infra
docker compose up -d
```

This spins up a PostgreSQL instance with the Apache AGE graph extension, creates the `bimatlas` graph, and bootstraps the schema (project, branch, revision, ifc_entity with JSONB attributes and SCD Type 2 columns, plus filter_sets, ifc_schema, validation_rule, merge_request, merge_conflict_log). It also starts **Adminer**, a web interface for viewing and querying the PostgreSQL database.

**Viewing the database with Adminer**

After `docker compose up -d`, open **http://localhost:8080** to use Adminer. Log in with:

| Field    | Value      |
| -------- | ---------- |
| System   | PostgreSQL |
| Server   | age-db     |
| Username | bimatlas   |
| Password | bimatlas   |
| Database | bimatlas   |

You can browse tables, run SQL, and inspect schema from the Adminer UI.

### 2. Run Migrations (Optional)

After the database is running, apply any incremental schema changes from `infra/migrations/`:

```bash
cd infra
./run_migrations.sh
```

This runs all `.sql` files in `infra/migrations/` in filename order (e.g. `001_*.sql`, `002_*.sql`). Use `psql` if available, or `docker compose exec` when running from the repo root. Override connection settings with env vars:

```
BIMATLAS_DB_HOST=localhost
BIMATLAS_DB_PORT=5432
BIMATLAS_DB_NAME=bimatlas
BIMATLAS_DB_USER=bimatlas
BIMATLAS_DB_PASSWORD=bimatlas
```

**Note:** The initial schema is created by `init-age.sql` when the container is first started. Migrations are for incremental changes (new columns, indexes, etc.) when upgrading.

### 3. Start the API

```bash
cd apps/api
pip install -r requirements.txt
./run.sh
```

The `run.sh` script loads environment variables from `.env` (if present) and starts the server. The GraphQL playground will be available at `http://localhost:8000/graphql`.

Optional: create `apps/api/.env` to override DB settings (defaults match Docker Compose):

```
BIMATLAS_DB_HOST=localhost
BIMATLAS_DB_PORT=5432
BIMATLAS_DB_NAME=bimatlas
BIMATLAS_DB_USER=bimatlas
BIMATLAS_DB_PASSWORD=bimatlas
PORT=8000
```

### 4. Start the Frontend

```bash
cd apps/web
pnpm install
pnpm run dev
```

The SvelteKit app will be available at `http://localhost:5173`.

---

## Key Concepts

### Projects and Branches

BimAtlas organises work into **projects** and **branches**, similar to Git:

- **Project** — A top-level container for a building model. Creating a project automatically creates a `main` branch.
- **Branch** — An independent timeline of revisions within a project. Each branch has its own version history, products, and graph data. Users can create additional branches (e.g. `structural-update`, `mep-revision`) for parallel design exploration.
- **Revision** — A snapshot created by uploading an IFC file to a branch. Uploading a new IFC into the same branch creates a new revision with diff-aware SCD Type 2 versioning.

**Workflow:**

1. Create a project (auto-creates `main` branch)
2. Upload IFC files into a branch → each upload creates a new revision
3. Create additional branches for parallel exploration
4. All queries (products, spatial tree, graph) are scoped to a specific branch

### IFC 4.3 Alignment

The type system mirrors the IFC 4.3 entity hierarchy from the buildingSMART standard:

```
IfcRoot (GlobalId, Name, Description)
  └─ IfcObjectDefinition
       └─ IfcObject (ObjectType)
            └─ IfcProduct (ObjectPlacement, Representation)
                 ├─ IfcElement (Tag) ─ physical elements (Wall, Slab, Beam, Column, ...)
                 └─ IfcSpatialElement ─ spatial containers (Site, Building, Storey, Space)
```

Graph nodes are labeled by their IFC class name. Graph edges are labeled by their IFC relationship entity name (e.g. `IfcRelAggregates`, `IfcRelContainedInSpatialStructure`).

### Versioning (SCD Type 2, per Branch)

Each IFC file upload creates a **revision** on a specific branch. Entities are versioned using Slowly Changing Dimension Type 2, scoped per branch:

- Only changed/added entities get new rows (detected via `content_hash` — SHA-256 of serialized attributes + geometry).
- Unchanged entities carry forward implicitly via their open `obsoleted_in_revision_id IS NULL` window.
- Revisions use a UUID primary key (`revision_id`) plus a monotonic `revision_seq` (SERIAL) for temporal ordering.
- The AGE graph mirrors this with `branch_id` (UUID string) and `revision_seq` on every node and edge.
- All GraphQL queries require a `branchId` (UUID string) and accept an optional `revision` (revision_seq integer), defaulting to latest on that branch.
- The `revisionDiff` query computes added/modified/deleted sets between any two revision sequences on the same branch.

### Two-Phase Ingestion

1. **Phase 1 — Spatial Structure:** Parse `IfcSpatialStructureElement` entities (Project, Site, Building, Storey, Space), insert as rows with NULL geometry, create graph nodes, and build the decomposition tree via `IfcRelAggregates` edges.
2. **Phase 2 — Elements + Geometry:** Extract triangulated meshes with IfcOpenShell, compute content hashes, diff against previous revision on the same branch, and insert only changed/added products. Close superseded rows and graph nodes.

### Geometry Pipeline

IFC geometry is extracted using IfcOpenShell with `USE_WORLD_COORDS` enabled (transforms baked in). Meshes are stored as a single PostgreSQL BYTEA column (`ifc_entity.geometry`) with vertices, normals, faces and matrix packed in a defined binary format, serialized through GraphQL as Base64 via a custom Strawberry scalar, and decoded on the frontend into `THREE.BufferGeometry`.

### Hybrid Storage

- **Relational table (`ifc_entity`):** UUID primary keys; IFC attributes in a single **JSONB** column (`attributes`) for flexible querying (GIN index); one **geometry BYTEA** column per entity. Scoped by `branch_id` with `created_in_revision_id` / `obsoleted_in_revision_id` for SCD Type 2.
- **AGE graph:** Topology and relationships where each vertex is labeled by IFC class and edges by IFC relationship entity name. Nodes/edges carry `branch_id` (UUID string) and `revision_seq` for temporal filtering. Enables Cypher traversals for relations, spatial trees, and connectivity queries.
- **GraphQL resolver** joins both sources into a unified `IfcProduct` response (IDs and attributes resolved from JSONB).

---

## GraphQL API

### Example Queries

**Fetch a single product on a branch (at latest revision):**

```graphql
query {
  ifcProduct(
    branchId: "550e8400-e29b-41d4-a716-446655440000"
    globalId: "2O2Fr$t4X7Zf8NOew3FL9r"
  ) {
    globalId
    ifcClass
    name
    containedIn {
      globalId
      ifcClass
      name
    }
    mesh {
      vertices
      normals
      faces
    }
    relations {
      globalId
      ifcClass
      relationship
    }
  }
}
```

**Spatial decomposition tree on a branch:**

```graphql
query {
  spatialTree(branchId: "550e8400-e29b-41d4-a716-446655440000") {
    globalId
    ifcClass
    name
    children {
      globalId
      ifcClass
      name
      containedElements {
        globalId
        ifcClass
        name
      }
    }
  }
}
```

**Time-travel to a specific revision on a branch (revision = revision_seq integer):**

```graphql
query {
  ifcProducts(
    branchId: "550e8400-e29b-41d4-a716-446655440000"
    ifcClass: "IfcWall"
    revision: 2
  ) {
    globalId
    name
  }
}
```

**Diff between revisions on a branch (fromRev/toRev = revision_seq):**

```graphql
query {
  revisionDiff(
    branchId: "550e8400-e29b-41d4-a716-446655440000"
    fromRev: 1
    toRev: 3
  ) {
    added {
      globalId
      ifcClass
      name
      changeType
    }
    modified {
      globalId
      ifcClass
      name
      changeType
    }
    deleted {
      globalId
      ifcClass
      name
      changeType
    }
  }
}
```

**List all projects (IDs are UUIDs):**

```graphql
query {
  projects {
    id
    name
    description
    branches {
      id
      name
    }
  }
}
```

**Create a project (mutation):**

```graphql
mutation {
  createProject(name: "Hospital Wing B", description: "New wing extension") {
    id
    name
    branches {
      id
      name
    }
  }
}
```

**Create a branch (mutation):**

```graphql
mutation {
  createBranch(
    projectId: "550e8400-e29b-41d4-a716-446655440000"
    name: "structural-update"
  ) {
    id
    name
  }
}
```

**Delete project, branch, or revision (mutations; IDs are UUID strings):**

```graphql
mutation {
  deleteProject(id: "550e8400-e29b-41d4-a716-446655440000")
}
mutation {
  deleteBranch(id: "6ba7b810-9dad-11d1-80b4-00c04fd430c8")
}
mutation {
  deleteRevision(id: "7c9e6679-7425-40de-944b-e07fc1f90ae7")
}
```

---

## Frontend

The SvelteKit app uses Svelte 5 runes for shared reactive state:

- **Project/Branch selector** — Header toolbar with project and branch dropdowns. Users select a project (or create one), then choose a branch to view.
- **Viewport** — Three.js canvas with snippet-based extensibility (`overlay`, `toolbar` props).
- **ForceGraph** — 3d-force-graph component for topological exploration, synced to shared selection state.
- **Selection state** — `activeProjectId`, `activeBranchId`, `activeGlobalId` and `activeRevision` as `$state` runes, importable from both `.svelte` and `.ts` files.

### Search and filters

Product search supports three filter modes:

- **Class** — Restrict by IFC product class (e.g. IfcWall, IfcSlab) via a combobox over the IFC product hierarchy.
- **Attribute** — Filter by attribute name and value (e.g. Name contains "A-101").
- **Relation** — Restrict to products connected in the AGE graph by a chosen IFC relationship type (e.g. IfcRelContainedInSpatialStructure, IfcRelAggregates). The backend queries the graph for all `global_id`s reachable via that edge type, then restricts the product stream to those IDs.

---

## Design Decisions

| Decision                       | Rationale                                                                           |
| ------------------------------ | ----------------------------------------------------------------------------------- |
| Projects + Branches            | Organises multi-building work and enables parallel design exploration (like Git)    |
| Branch-scoped SCD Type 2       | Each branch has independent version history; diffs are per-branch                   |
| Binary via Base64 in GraphQL   | Avoids JSON overhead for large meshes while remaining GraphQL-compatible            |
| `USE_WORLD_COORDS`             | Eliminates client-side transform matrix application; simpler Three.js code          |
| Snippet extensibility          | `Viewport.svelte` accepts `Snippet` props for pluggable UI without subclassing      |
| AGE + relational hybrid        | Attributes/blobs in SQL for fast retrieval; topology in graph for Cypher traversals |
| JSONB attributes on ifc_entity | Single flexible column for IFC attributes; GIN index for filter/query performance   |
| SCD Type 2 + tagged graph      | Avoids duplicating 100k+ unchanged elements per revision; enables full time-travel  |
| Spatial structure first-class  | Enforces IFC 4.3 constraint: one physical element per single spatial container      |

---

## Testing

BimAtlas includes comprehensive backend unit tests using pytest with an isolated test database.

### Quick Start

```bash
cd apps/api
./setup_test_db.sh  # One-time setup
./run_tests.sh      # Run tests
```

### Features

- **85+ comprehensive unit tests** covering all backend components
- **Isolated test database** (`bimatlas_test`) - never affects production/development data
- **Fast execution** (~5 seconds for full test suite)
- **CI/CD ready** with automated setup/teardown
- **Comprehensive coverage** (geometry, ingestion, API, database, SCD Type 2)

### Test Structure

```
apps/api/tests/
├── test_geometry.py      # IFC parsing and geometry extraction
├── test_ingestion.py     # Ingestion pipeline and diff logic
├── test_api.py           # FastAPI endpoints
├── test_db.py            # Database operations and queries
└── conftest.py           # Pytest fixtures and configuration
```

### Common Commands

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_api.py

# Run in parallel (fast!)
pytest -n auto  # Requires: uv pip install pytest-xdist
```

### Documentation

- **Full Guide:** [apps/api/tests/README.md](apps/api/tests/README.md)

### Frontend (Playwright) — Table / spreadsheet tests

The table view has an isolated Playwright suite that uses dummy fixture data (no backend or IFC stream required). From `apps/web/`:

```bash
# Install Playwright browsers (one-time)
pnpm exec playwright install chromium

# Headless run (CI / default)
pnpm run test:spreadsheet

# Headed run: open Chromium so you can watch edits (lock/unlock, sheet rows)
pnpm run test:spreadsheet:headed
```

Tests live in `apps/web/tests/table-spreadsheet/` and target `/table?fixture=1`.

---

## License

See [LICENSE](./LICENSE).
