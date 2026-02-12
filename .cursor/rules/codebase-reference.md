# BimAtlas Codebase Reference

> Extensible Spatial-Graph Engine for IFC 4.3 Building Models.  
> This file is the authoritative map for agents navigating the codebase.

---

## Tech Stack

| Layer | Technology | Notes |
|---|---|---|
| Frontend | SvelteKit 5 (Svelte 5 runes), TypeScript | Three.js for 3D, 3d-force-graph for topology, urql GraphQL client |
| API | FastAPI + Strawberry GraphQL (Python 3.11+) | Mounted at `/graphql`, health check at `/health`, REST upload at `/upload-ifc` |
| Database | PostgreSQL + Apache AGE | Relational tables + graph in one DB, Cypher via `SELECT * FROM cypher(...)` |
| IFC Parser | IfcOpenShell | Geometry extraction, mesh triangulation, spatial structure parsing |
| Package Mgmt | `uv` / `pip` (API), `npm` (web) | API deps in `pyproject.toml` + `requirements.txt` |
| Infra | Docker Compose | Single container: `apache/age:latest` |

---

## Directory Layout

```
BimAtlas/
├── apps/
│   ├── api/                          # Python backend
│   │   ├── src/
│   │   │   ├── main.py               # FastAPI entry, Strawberry mount, mutations, lifespan
│   │   │   ├── config.py             # DB env vars (BIMATLAS_DB_*)
│   │   │   ├── db.py                 # Connection pool, cursor helper, all SQL queries, project/branch/revision CRUD
│   │   │   ├── schema/               # GraphQL types + resolvers
│   │   │   │   ├── queries.py        # Root Query + Mutation (project/branch/IFC queries)
│   │   │   │   ├── ifc_types.py      # Strawberry types (IFC 4.3 hierarchy + Project/Branch + versioning)
│   │   │   │   ├── ifc_enums.py      # IfcRelationshipType, IfcProductCategory enums
│   │   │   │   ├── scalars.py        # Base64Bytes custom scalar
│   │   │   │   └── mesh_types.py     # Re-export of IfcMeshRepresentation
│   │   │   └── services/
│   │   │       ├── ifc/
│   │   │       │   ├── geometry.py    # IFC mesh extraction + IfcProductRecord dataclass
│   │   │       │   └── ingestion.py   # Versioned two-phase ingestion pipeline (branch-scoped)
│   │   │       └── graph/
│   │   │           ├── age_client.py  # AGE Cypher executor, read+write, label mgmt (branch-scoped)
│   │   │           └── queries.py     # Cypher query templates (str.format)
│   │   ├── tests/                     # pytest unit tests (85+ tests)
│   │   │   ├── conftest.py            # Test fixtures, test_branch helper
│   │   │   ├── test_api.py            # FastAPI endpoint tests
│   │   │   ├── test_db.py             # Database query tests
│   │   │   ├── test_ingestion.py      # Ingestion pipeline tests
│   │   │   └── test_geometry.py       # IFC parsing tests
│   │   ├── pyproject.toml
│   │   ├── requirements.txt
│   │   └── run.sh                     # Starts uvicorn (loads .env)
│   │
│   └── web/                           # SvelteKit frontend
│       ├── src/
│       │   ├── routes/
│       │   │   ├── +page.svelte       # Main page: project picker, 3D Viewport / Graph toggle
│       │   │   └── +layout.svelte     # Root layout
│       │   └── lib/
│       │       ├── engine/            # Three.js scene (SceneManager, BufferGeometryLoader)
│       │       ├── graph/             # ForceGraph.svelte, graphStore.svelte.ts
│       │       ├── ui/               # Viewport.svelte, SelectionPanel.svelte, ImportModal.svelte
│       │       ├── state/            # selection.svelte.ts (shared $state runes: project, branch, revision, selection)
│       │       └── api/              # GraphQL client (urql), queries and mutations
│       └── package.json
│
└── infra/
    ├── docker-compose.yml             # PostgreSQL/AGE container
    └── init-age.sql                   # DDL: projects, branches, revisions, ifc_products (SCD2), indexes
```

---

## API Layer (`apps/api/src/`)

### Entry Point

- **`main.py`** -- FastAPI app with Strawberry GraphQL at `/graphql`, REST upload at `/upload-ifc`. Uses a `lifespan` context manager that calls `init_pool()` / `close_pool()`. CORS is wide-open (`*`).

### Configuration

- **`config.py`** -- All settings via `os.getenv()` with `BIMATLAS_` prefix. Defaults match the Docker Compose service.
  - `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`
  - `AGE_GRAPH` (graph name, default `"bimatlas"`)

### Database (`db.py`)

Connection pool and all relational SQL lives here. **All product/revision queries are now branch-scoped.**

| Function | Purpose |
|---|---|
| `init_pool()` / `close_pool()` | Lifecycle (called by `main.py` lifespan) |
| `get_conn()` / `put_conn()` | Raw pool access (used by `age_client.py` and `ingestion.py`) |
| `get_cursor(dict_cursor=)` | Context manager with auto commit/rollback |
| **Project Management** | |
| `create_project(name, description?)` | Creates a project with auto-created `main` branch. Returns project dict |
| `fetch_projects()` | All projects ordered by created_at DESC |
| `fetch_project(project_id)` | Single project by id |
| **Branch Management** | |
| `create_branch(project_id, name)` | Creates a new branch in a project. Returns branch dict |
| `fetch_branches(project_id)` | All branches for a project, ordered by created_at |
| `fetch_branch(branch_id)` | Single branch by id |
| `fetch_branch_by_name(project_id, name)` | Single branch by project+name |
| **Revision Queries (branch-scoped)** | |
| `get_latest_revision_id(branch_id)` | Returns `MAX(id)` from `revisions` on a branch |
| `fetch_revisions(branch_id)` | All revisions on a branch, ordered by id |
| **Product Queries (branch + revision scoped)** | |
| `fetch_product_at_revision(global_id, rev, branch_id)` | Single product at revision on branch (SCD2 filter) |
| `fetch_products_at_revision(rev, branch_id, ifc_class?, contained_in?)` | Filtered product list |
| `fetch_spatial_container(gid, rev, branch_id)` | Lookup spatial container by GlobalId |
| `fetch_revision_diff(from_rev, to_rev, branch_id)` | Returns `{added, modified, deleted}` dicts |

The SCD2 revision filter used throughout:
```sql
branch_id = :branch_id 
AND valid_from_rev <= :rev 
AND (valid_to_rev IS NULL OR valid_to_rev > :rev)
```

### GraphQL Schema (`schema/`)

**Types (`ifc_types.py`)** -- mirrors the IFC 4.3 entity hierarchy + project/branch management:

| Type | Role |
|---|---|
| `IfcRoot` (interface) | `global_id`, `name`, `description` |
| `IfcObjectDefinition` (interface) | Extends IfcRoot |
| `IfcProduct` (type) | Main query return type. Adds `ifc_class`, `object_type`, `tag`, `contained_in`, `mesh`, `relations` |
| `IfcMeshRepresentation` | `vertices`, `normals`, `faces` as `Base64Bytes` |
| `IfcRelatedProduct` | Related product reference with `relationship` enum |
| `IfcSpatialContainerRef` | Spatial container reference |
| `IfcSpatialNode` | Recursive tree node with `children` + `contained_elements` |
| `Revision` | `id`, `branch_id`, `label`, `ifc_filename`, `created_at` |
| `RevisionDiff` | `from_revision`, `to_revision`, `added[]`, `modified[]`, `deleted[]` |
| `RevisionDiffEntry` | `global_id`, `ifc_class`, `name`, `change_type` |
| `ChangeType` (enum) | `ADDED`, `MODIFIED`, `DELETED` |
| **`Project`** | `id`, `name`, `description`, `created_at`, `branches[]` |
| **`Branch`** | `id`, `project_id`, `name`, `created_at` |

**Enums (`ifc_enums.py`)**:

| Enum | Values |
|---|---|
| `IfcRelationshipType` | `REL_AGGREGATES`, `REL_CONTAINED_IN_SPATIAL`, `REL_CONNECTS_ELEMENTS`, `REL_VOIDS_ELEMENT`, `REL_FILLS_ELEMENT`, `REL_ASSOCIATES_MATERIAL`, `REL_DEFINES_BY_TYPE` |
| `IfcProductCategory` | `WALL`, `SLAB`, `BEAM`, `COLUMN`, `DOOR`, `WINDOW`, etc. (22 values) |

**Scalars (`scalars.py`)** -- `Base64Bytes`: serializes `bytes` as Base64 strings in GraphQL.

**Root Query (`queries.py`)** -- all IFC queries require `branchId`, accept optional `revision`:

| Field | Args | Returns |
|---|---|---|
| **Project/Branch Queries** | | |
| `projects` | (none) | `[Project]` with nested branches |
| `project` | `projectId` | `Project?` |
| `branches` | `projectId` | `[Branch]` |
| **IFC Queries (branch-scoped)** | | |
| `ifcProduct` | `branchId`, `globalId`, `revision?` | `IfcProduct?` |
| `ifcProducts` | `branchId`, `ifcClass?`, `containedIn?`, `revision?` | `[IfcProduct]` |
| `spatialTree` | `branchId`, `revision?` | `[IfcSpatialNode]` |
| `revisions` | `branchId` | `[Revision]` |
| `revisionDiff` | `branchId`, `fromRev`, `toRev` | `RevisionDiff` |

**Mutations (`queries.py`)**:

| Mutation | Args | Returns |
|---|---|---|
| `createProject` | `name`, `description?` | `Project` (with auto-created `main` branch) |
| `createBranch` | `projectId`, `name` | `Branch` |

Key internal helpers in `queries.py`:
- `_resolve_revision(branch_id, revision)` -- defaults `None` to `get_latest_revision_id(branch_id)`
- `_row_to_product(row, rev, branch_id)` -- enriches a DB dict with mesh, container ref, and graph relations
- `_dict_to_spatial_node(d)` -- recursively converts tree dicts to `IfcSpatialNode`
- `_to_iso(dt)` -- datetime to ISO 8601 string

### IFC Services (`services/ifc/`)

**`geometry.py`** -- IFC mesh extraction:

| Export | Purpose |
|---|---|
| `IfcProductRecord` (dataclass) | Maps 1:1 to an `ifc_products` row. Fields: `global_id`, `ifc_class`, `name`, `description`, `object_type`, `tag`, `contained_in`, `vertices`, `normals`, `faces`, `matrix`, `content_hash` |
| `extract_products(ifc_path)` | Opens IFC file, returns list of `IfcProductRecord` |
| `extract_products_from_model(model)` | Same but accepts an already-opened `ifcopenshell.file` (avoids double-open) |

Internal functions: `_compute_content_hash(...)`, `_build_containment_map(model)`, `_extract_spatial_elements(model, map)`, `_extract_geometric_elements(model, map)`.

**`ingestion.py`** -- versioned two-phase ingestion pipeline (branch-scoped):

| Export | Purpose |
|---|---|
| `ingest_ifc(ifc_path, branch_id, label?)` | Main entry point. Requires branch_id. Returns `IngestionResult` |
| `IngestionResult` (dataclass) | `revision_id`, `branch_id`, `total_products`, `added`, `modified`, `deleted`, `unchanged`, `edges_created` |
| `IfcRelationshipRecord` (dataclass) | `from_global_id`, `to_global_id`, `relationship_type` |

The pipeline:
1. Opens IFC model once, extracts products + relationships
2. Creates a `revisions` row on the branch (single relational transaction for steps 2-5)
3. Loads current `content_hash` values for the branch, diffs against new products
4. Closes SCD2 rows for modified/deleted products on the branch
5. Inserts new SCD2 rows for added/modified products on the branch
6. Closes graph nodes + edges for modified/deleted (best-effort, branch-scoped)
7. Creates graph nodes for added/modified (branch-scoped)
8. Creates graph edges for relationships involving changed products (branch-scoped)

Relationships extracted: `IfcRelAggregates`, `IfcRelContainedInSpatialStructure`, `IfcRelVoidsElement`, `IfcRelFillsElement`, `IfcRelConnectsElements`.

### Graph Services (`services/graph/`)

**`age_client.py`** -- AGE Cypher executor with read and write operations (all branch-scoped):

| Function | Category | Purpose |
|---|---|---|
| `get_relations(global_id, rev, branch_id)` | Read | Outgoing + incoming relations at revision on branch |
| `get_spatial_tree_roots(rev, branch_id)` | Read | IfcProject nodes at revision on branch |
| `get_spatial_children(global_id, rev, branch_id)` | Read | Children via IfcRelAggregates |
| `get_contained_elements(spatial_gid, rev, branch_id)` | Read | Elements via IfcRelContainedInSpatialStructure |
| `build_spatial_tree(rev, branch_id)` | Read | Full recursive tree from roots |
| `create_node(ifc_class, global_id, name, rev_id, branch_id)` | Write | New revision-tagged, branch-scoped node |
| `close_node(global_id, rev_id, branch_id)` | Write | Set `valid_to_rev` on current node |
| `create_edge(from_gid, to_gid, rel_type, rev_id, branch_id)` | Write | New revision-tagged, branch-scoped edge |
| `close_edges_for_node(global_id, rev_id, branch_id)` | Write | Close all edges for a node |

Internal helpers:
- `_rev_filter(alias, rev, branch_id)` -- generates Cypher `WHERE` clause for revision + branch visibility
- `_exec_cypher(cypher, cols)` -- read queries via AGE SQL interface
- `_exec_cypher_write(cypher)` -- write queries (must include `RETURN`)
- `_ensure_vlabel(label)` / `_ensure_elabel(label)` -- auto-creates AGE labels with caching
- `_validate_id(value)` -- validates GlobalIds for safe Cypher embedding
- `_validate_label(label)` -- validates IFC class names as AGE labels
- `_escape_cypher_string(value)` -- escapes strings for Cypher literals

**`queries.py`** -- Cypher templates using `str.format()` placeholders:
- `NEIGHBORS_OUT`, `NEIGHBORS_IN` -- relation traversal (Cypher templates)
- `SPATIAL_ROOTS` -- IfcProject nodes
- `SPATIAL_CHILDREN` -- decomposition children
- `CONTAINED_ELEMENTS` -- containment query

---

## Database Schema (`infra/init-age.sql`)

### Tables

**`projects`** -- top-level project container:
- `id SERIAL PK`, `name TEXT NOT NULL`, `description TEXT`, `created_at TIMESTAMPTZ`

**`branches`** -- independent timelines within a project:
- `id SERIAL PK`, `project_id INT NOT NULL FK`, `name TEXT NOT NULL`, `created_at TIMESTAMPTZ`
- `UNIQUE(project_id, name)`

**`revisions`** -- one row per IFC file upload (scoped to branch):
- `id SERIAL PK`, `branch_id INT NOT NULL FK`, `label TEXT`, `ifc_filename TEXT NOT NULL`, `created_at TIMESTAMPTZ`

**`ifc_products`** -- SCD Type 2 versioned product rows (scoped to branch):
- `id SERIAL PK` (surrogate, multiple rows per `global_id`)
- `branch_id INT NOT NULL FK` -- all products scoped to a branch
- IFC attributes: `global_id`, `ifc_class`, `name`, `description`, `object_type`, `tag`, `contained_in`
- Geometry BYTEAs: `vertices`, `normals`, `faces`, `matrix`
- Versioning: `content_hash TEXT NOT NULL`, `valid_from_rev INT NOT NULL FK`, `valid_to_rev INT FK`
- `UNIQUE(branch_id, global_id, valid_from_rev)`

### Key Indexes
- `idx_branches_project` -- `(project_id)`
- `idx_revisions_branch` -- `(branch_id)`
- `idx_ifc_products_current` -- `(branch_id, global_id) WHERE valid_to_rev IS NULL`
- `idx_ifc_products_class` -- `(branch_id, ifc_class, valid_to_rev)`
- `idx_ifc_products_contained` -- `(branch_id, contained_in) WHERE valid_to_rev IS NULL`
- `idx_ifc_products_rev_range` -- `(branch_id, valid_from_rev, valid_to_rev)`

### Graph (Apache AGE)

- Graph name: `bimatlas` (or `bimatlas_test` for tests)
- Node labels: IFC class names (e.g. `IfcWall`, `IfcBuildingStorey`)
- Edge labels: IFC relationship names (e.g. `IfcRelAggregates`, `IfcRelContainedInSpatialStructure`)
- **All nodes/edges carry**: `branch_id INT`, `valid_from_rev INT`, `valid_to_rev INT` (`-1` = current, AGE has no NULL props)
- Nodes carry: `global_id`, `name`

---

## Frontend (`apps/web/src/`)

### Routing
- **`+layout.svelte`** -- root layout
- **`+page.svelte`** -- main app page with project picker, project/branch selectors, 3D View / Graph toggle tabs

### Key Libraries (`lib/`)

| Module | File(s) | Purpose |
|---|---|---|
| `engine/` | `SceneManager.ts`, `BufferGeometryLoader.ts` | Three.js lifecycle, mesh registry, highlight, camera. `BufferGeometryLoader` decodes Base64 to `THREE.BufferGeometry` |
| `graph/` | `ForceGraph.svelte`, `graphStore.svelte.ts` | 3d-force-graph wrapper. Node clicks sync to shared selection state. Fetches branch-scoped spatial tree |
| `ui/` | `Viewport.svelte`, `SelectionPanel.svelte`, `ImportModal.svelte` | Viewport accepts `{overlay?, toolbar?}` Snippet props for extensibility |
| `state/` | `selection.svelte.ts` | Shared reactive state using Svelte 5 `$state` runes: `getSelection()` (activeGlobalId), `getRevisionState()` (activeRevision), **`getProjectState()`** (activeProjectId, activeBranchId) |
| `api/` | `client.ts` | urql GraphQL client pointing at `/graphql`. Contains all queries and mutations |

### GraphQL Queries/Mutations (`lib/api/client.ts`)

**Project/Branch:**
- `PROJECTS_QUERY` -- fetch all projects with branches
- `PROJECT_QUERY` -- single project by id
- `BRANCHES_QUERY` -- branches for a project
- `CREATE_PROJECT_MUTATION` -- create project (returns project with auto-created `main` branch)
- `CREATE_BRANCH_MUTATION` -- create branch in a project

**IFC Queries (all require `branchId`):**
- `IFC_PRODUCT_QUERY` -- single product with mesh + relations
- `IFC_PRODUCTS_QUERY` -- list products with optional filters
- `SPATIAL_TREE_QUERY` -- spatial decomposition tree
- `REVISIONS_QUERY` -- list revisions on a branch
- `REVISION_DIFF_QUERY` -- diff between two revisions on a branch

### Conventions
- **Svelte 5 runes only** -- use `$state`, `$derived`, `$effect`, `$props`. No legacy `$:` or stores.
- **Snippet extensibility** -- `Viewport.svelte` accepts `Snippet` typed props (`overlay`, `toolbar`) via `{@render}`.
- **State access pattern** -- `getSelection()` / `getRevisionState()` / `getProjectState()` return getter/setter objects importable from both `.svelte` and `.ts` files.
- **State reset cascade** -- changing project resets branch/revision/selection; changing branch resets revision/selection.

---

## Core Patterns & Conventions

### Projects and Branches
- **Project** -- top-level container for a building model. Creating a project auto-creates a `main` branch.
- **Branch** -- independent timeline of revisions within a project. Each branch has its own version history, products, and graph data.
- **Revision** -- snapshot created by uploading an IFC file to a branch.
- **Workflow**: Create project → select branch → upload IFC files → each upload creates a new revision on that branch.

### Versioning (SCD Type 2, per Branch)
- Every IFC upload creates a `revisions` row linked to a branch.
- Only changed products get new `ifc_products` rows (detected via `content_hash`).
- Unchanged products carry forward via open `valid_to_rev IS NULL` window.
- Graph mirrors this with `branch_id`, `valid_from_rev`/`valid_to_rev` on every node and edge.
- All queries require `branchId` and accept optional `revision` param; default = latest on that branch.
- `revision_diff` computes added/modified/deleted between any two revisions on the same branch.

### IFC 4.3 Alignment
- Type hierarchy: `IfcRoot` -> `IfcObjectDefinition` -> `IfcProduct`
- Graph node labels = IFC class names (e.g. `IfcWall`)
- Graph edge labels = IFC relationship entity names (e.g. `IfcRelAggregates`)
- Spatial containment: one physical element per single spatial container (IFC 4.3 sec 4.1.5.13)

### Geometry Pipeline
- IfcOpenShell with `USE_WORLD_COORDS = True` (transforms baked in)
- Stored as BYTEA in Postgres, serialized as Base64 in GraphQL
- Frontend decodes to `Float32Array`/`Uint32Array` -> `THREE.BufferGeometry`

### Graph Access Pattern
- Cypher executed via AGE's SQL interface: `SELECT * FROM cypher('bimatlas', $$ ... $$) AS (col agtype)`
- Always `LOAD 'age'` and `SET search_path = ag_catalog, "$user", public` before Cypher
- Labels must be created before use (`create_vlabel`/`create_elabel` -- handled automatically by `_ensure_vlabel`/`_ensure_elabel` with caching)

### Connection Management
- `db.py` provides `get_conn()`/`put_conn()` for raw access, `get_cursor()` for managed transactions
- `age_client.py` gets its own connections per Cypher call (graph ops are separate transactions)
- `ingestion.py` uses a single cursor for all relational ops (atomic), then best-effort graph ops

---

## Running the Project

```bash
# 1. Database
cd infra && docker compose up -d

# 2. API (from apps/api/)
pip install -r requirements.txt   # or: uv sync
./run.sh                          # uvicorn on port 8000

# 3. Frontend (from apps/web/)
npm install && npm run dev        # vite on port 5173
```

GraphQL playground: `http://localhost:8000/graphql`  
Frontend: `http://localhost:5173`

---

## Testing

All tests are in `apps/api/tests/`. Use the test fixtures to get a pre-configured test branch:

```python
def test_something(test_branch):
    """test_branch fixture provides a branch_id in the test database."""
    branch_id = test_branch
    # Use branch_id in your test
```

Run tests:
```bash
cd apps/api
./run_tests.sh           # Full test suite
pytest tests/test_db.py  # Specific file
```

Key test fixtures in `conftest.py`:
- `test_branch` -- creates a project+branch, returns branch_id (use this in most tests!)
- `api_branch` -- same but for API endpoint tests
- `db_pool` -- initializes connection pool with test database
- `age_graph` -- configures AGE client to use test graph
- `clean_db` -- truncates all tables before each test
- `test_ifc_file` -- path to sample IFC file

---

## Key Architectural Decisions

| Decision | Rationale |
|---|---|
| Projects + Branches | Organises multi-building work and enables parallel design exploration (like Git) |
| Branch-scoped SCD Type 2 | Each branch has independent version history; diffs are per-branch |
| Auto-create `main` branch | Every project gets a default branch to upload IFC files into |
| Binary via Base64 in GraphQL | Avoids JSON overhead for large meshes while remaining GraphQL-compatible |
| `USE_WORLD_COORDS` | Eliminates client-side transform matrix application; simpler Three.js code |
| Snippet extensibility | `Viewport.svelte` accepts `Snippet` props for pluggable UI without subclassing |
| AGE + relational hybrid | Attributes/blobs in SQL for fast retrieval; topology in graph for Cypher traversals |
| SCD Type 2 + tagged graph | Avoids duplicating 100k+ unchanged elements per revision; enables full time-travel |
| Spatial structure first-class | Enforces IFC 4.3 constraint: one physical element per single spatial container |
