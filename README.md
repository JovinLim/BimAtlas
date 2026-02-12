# BimAtlas

**Extensible Spatial-Graph Engine for IFC Building Models**

BimAtlas ingests IFC 4.3 files into a versioned PostgreSQL + Apache AGE graph database, exposes them through a GraphQL API, and renders geometry and topology in a SvelteKit frontend powered by Three.js and 3d-force-graph.

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

**Data flow:** IFC file upload → versioned ingestion (SCD Type 2 diff) → relational rows + revision-tagged graph nodes/edges → GraphQL resolvers (revision-scoped) → frontend decodes Base64 geometry into `THREE.BufferGeometry` and renders the spatial/topological graph.

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
          ui/                   # Viewport, SelectionPanel (snippet extensibility)
          state/                # Shared reactive state ($state runes)
          api/                  # GraphQL client
        routes/
      package.json

    api/                        # FastAPI + Strawberry GraphQL
      src/
        main.py                 # App entry, mounts Strawberry router
        config.py               # DB connection settings
        db.py                   # Postgres/AGE connection pool (psycopg2)
        services/
          ifc/
            geometry.py         # IfcOpenShell mesh extraction
            ingestion.py        # Two-phase versioned IFC ingestion
          graph/
            age_client.py       # AGE Cypher query builder/executor
            queries.py          # Reusable Cypher query templates
        schema/
          ifc_types.py          # IFC 4.3-aligned Strawberry types
          ifc_enums.py          # Relationship & element class enums
          mesh_types.py         # MeshData type for geometry blobs
          queries.py            # Root Query resolver
          scalars.py            # Base64 scalar for binary blobs
      pyproject.toml
      requirements.txt
      run.sh                   # Start server (loads .env)

  infra/
    docker-compose.yml          # PostgreSQL/AGE container
    init-age.sql                # Bootstrap: AGE extension + versioned schema
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

This spins up a PostgreSQL instance with the Apache AGE graph extension, creates the `bimatlas` graph, and bootstraps the versioned schema (`revisions` + `ifc_products` with SCD Type 2 columns).

### 2. Start the API

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

### 3. Start the Frontend

```bash
cd apps/web
npm install
npm run dev
```

The SvelteKit app will be available at `http://localhost:5173`.

---

## Key Concepts

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

### Versioning (SCD Type 2)

Each IFC file upload creates a **revision**. Products are versioned using Slowly Changing Dimension Type 2:

- Only changed/added products get new rows (detected via `content_hash` — SHA-256 of serialized attributes + geometry).
- Unchanged products carry forward implicitly via their open `valid_to_rev IS NULL` window.
- The AGE graph mirrors this with `valid_from_rev` / `valid_to_rev` properties on every node and edge.
- All GraphQL queries accept an optional `revision` parameter, defaulting to latest.
- The `revisionDiff` query computes added/modified/deleted sets between any two revisions.

### Two-Phase Ingestion

1. **Phase 1 — Spatial Structure:** Parse `IfcSpatialStructureElement` entities (Project, Site, Building, Storey, Space), insert as rows with NULL geometry, create graph nodes, and build the decomposition tree via `IfcRelAggregates` edges.
2. **Phase 2 — Elements + Geometry:** Extract triangulated meshes with IfcOpenShell, compute content hashes, diff against previous revision, and insert only changed/added products. Close superseded rows and graph nodes.

### Geometry Pipeline

IFC geometry is extracted using IfcOpenShell with `USE_WORLD_COORDS` enabled (transforms baked in). Meshes are stored as PostgreSQL BYTEA columns (vertices, normals, faces as typed arrays), serialized through GraphQL as Base64 strings via a custom Strawberry scalar, and decoded on the frontend into `THREE.BufferGeometry` for direct GPU upload.

### Hybrid Storage

- **Relational table (`ifc_products`):** IFC attributes and binary geometry blobs for efficient retrieval.
- **AGE graph:** Topology and relationships where each vertex is labeled by IFC class and edges by IFC relationship entity name. Enables Cypher traversals for neighbors, spatial trees, and connectivity queries.
- **GraphQL resolver** joins both sources into a unified `IfcProduct` response.

---

## GraphQL API

### Example Queries

**Fetch a single product (at latest revision):**

```graphql
query {
  ifcProduct(globalId: "2O2Fr$t4X7Zf8NOew3FL9r") {
    globalId
    ifcClass
    name
    containedIn { globalId ifcClass name }
    mesh { vertices normals faces }
    neighbors { globalId ifcClass relationship }
  }
}
```

**Spatial decomposition tree:**

```graphql
query {
  spatialTree {
    globalId
    ifcClass
    name
    children {
      globalId
      ifcClass
      name
      containedElements { globalId ifcClass name }
    }
  }
}
```

**Time-travel to a specific revision:**

```graphql
query {
  ifcProducts(ifcClass: "IfcWall", revision: 2) {
    globalId
    name
  }
}
```

**Diff between revisions:**

```graphql
query {
  revisionDiff(fromRev: 1, toRev: 3) {
    added { globalId ifcClass name changeType }
    modified { globalId ifcClass name changeType }
    deleted { globalId ifcClass name changeType }
  }
}
```

---

## Frontend

The SvelteKit app uses Svelte 5 runes for shared reactive state:

- **Viewport** — Three.js canvas with snippet-based extensibility (`overlay`, `toolbar` props).
- **ForceGraph** — 3d-force-graph component for topological exploration, synced to shared selection state.
- **Selection state** — `activeGlobalId` and `activeRevision` as `$state` runes, importable from both `.svelte` and `.ts` files.

---

## Design Decisions

| Decision | Rationale |
|---|---|
| Binary via Base64 in GraphQL | Avoids JSON overhead for large meshes while remaining GraphQL-compatible |
| `USE_WORLD_COORDS` | Eliminates client-side transform matrix application; simpler Three.js code |
| Snippet extensibility | `Viewport.svelte` accepts `Snippet` props for pluggable UI without subclassing |
| AGE + relational hybrid | Attributes/blobs in SQL for fast retrieval; topology in graph for Cypher traversals |
| SCD Type 2 + tagged graph | Avoids duplicating 100k+ unchanged elements per revision; enables full time-travel |
| Spatial structure first-class | Enforces IFC 4.3 constraint: one physical element per single spatial container |

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

- ✅ **85+ comprehensive unit tests** covering all backend components
- ✅ **Isolated test database** (`bimatlas_test`) - never affects production/development data
- ✅ **Fast execution** (~5 seconds for full test suite)
- ✅ **CI/CD ready** with automated setup/teardown
- ✅ **Comprehensive coverage** (geometry, ingestion, API, database, SCD Type 2)

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

- **Quick Start:** [apps/api/tests/QUICKSTART.md](apps/api/tests/QUICKSTART.md)
- **Full Guide:** [apps/api/tests/README.md](apps/api/tests/README.md)
- **Migration Guide:** [apps/api/tests/MIGRATION.md](apps/api/tests/MIGRATION.md)
- **Summary:** [TESTING_SUMMARY.md](TESTING_SUMMARY.md)

---

## License

See [LICENSE](./LICENSE).
