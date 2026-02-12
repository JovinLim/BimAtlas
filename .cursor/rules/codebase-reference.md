# BimAtlas Codebase Reference

> Extensible Spatial-Graph Engine for IFC 4.3 Building Models.  
> This file is the authoritative map for agents navigating the codebase.

---

## Tech Stack

| Layer | Technology | Notes |
|---|---|---|
| Frontend | SvelteKit 5 (Svelte 5 runes), TypeScript | Three.js for 3D, 3d-force-graph for topology, urql GraphQL client |
| API | FastAPI + Strawberry GraphQL (Python 3.11+) | Mounted at `/graphql`, health check at `/health` |
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
│   │   │   ├── main.py               # FastAPI entry, Strawberry mount, lifespan
│   │   │   ├── config.py             # DB env vars (BIMATLAS_DB_*)
│   │   │   ├── db.py                 # Connection pool, cursor helper, all SQL queries
│   │   │   ├── schema/               # GraphQL types + resolvers
│   │   │   │   ├── queries.py        # Root Query (5 fields)
│   │   │   │   ├── ifc_types.py      # Strawberry types (IFC 4.3 hierarchy + versioning)
│   │   │   │   ├── ifc_enums.py      # IfcRelationshipType, IfcProductCategory enums
│   │   │   │   ├── scalars.py        # Base64Bytes custom scalar
│   │   │   │   └── mesh_types.py     # Re-export of IfcMeshRepresentation
│   │   │   └── services/
│   │   │       ├── ifc/
│   │   │       │   ├── geometry.py    # IFC mesh extraction + IfcProductRecord dataclass
│   │   │       │   └── ingestion.py   # Versioned two-phase ingestion pipeline
│   │   │       └── graph/
│   │   │           ├── age_client.py  # AGE Cypher executor, read+write, label mgmt
│   │   │           └── queries.py     # Cypher query templates (str.format)
│   │   ├── pyproject.toml
│   │   ├── requirements.txt
│   │   └── run.sh                     # Starts uvicorn (loads .env)
│   │
│   └── web/                           # SvelteKit frontend
│       ├── src/
│       │   ├── routes/
│       │   │   ├── +page.svelte       # Main page: 3D Viewport / Graph toggle
│       │   │   └── +layout.svelte     # Root layout
│       │   └── lib/
│       │       ├── engine/            # Three.js scene (SceneManager, BufferGeometryLoader)
│       │       ├── graph/             # ForceGraph.svelte, graphStore.svelte.ts
│       │       ├── ui/               # Viewport.svelte, SelectionPanel.svelte
│       │       ├── state/            # selection.svelte.ts (shared $state runes)
│       │       └── api/              # GraphQL client (urql)
│       └── package.json
│
└── infra/
    ├── docker-compose.yml             # PostgreSQL/AGE container
    └── init-age.sql                   # DDL: revisions table, ifc_products (SCD2), indexes
```

---

## API Layer (`apps/api/src/`)

### Entry Point

- **`main.py`** -- FastAPI app with Strawberry GraphQL at `/graphql`. Uses a `lifespan` context manager that calls `init_pool()` / `close_pool()`. CORS is wide-open (`*`).

### Configuration

- **`config.py`** -- All settings via `os.getenv()` with `BIMATLAS_` prefix. Defaults match the Docker Compose service.
  - `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`
  - `AGE_GRAPH` (graph name, default `"bimatlas"`)

### Database (`db.py`)

Connection pool and all relational SQL lives here. Key exports:

| Function | Purpose |
|---|---|
| `init_pool()` / `close_pool()` | Lifecycle (called by `main.py` lifespan) |
| `get_conn()` / `put_conn()` | Raw pool access (used by `age_client.py` and `ingestion.py`) |
| `get_cursor(dict_cursor=)` | Context manager with auto commit/rollback |
| `get_latest_revision_id()` | Returns `MAX(id)` from `revisions` |
| `fetch_revisions()` | All revisions ordered by id |
| `fetch_product_at_revision(global_id, rev)` | Single product at revision (SCD2 filter) |
| `fetch_products_at_revision(rev, ifc_class?, contained_in?)` | Filtered product list |
| `fetch_spatial_container(gid, rev)` | Lookup spatial container by GlobalId |
| `fetch_revision_diff(from_rev, to_rev)` | Returns `{added, modified, deleted}` dicts |

The SCD2 revision filter used throughout:
```sql
valid_from_rev <= :rev AND (valid_to_rev IS NULL OR valid_to_rev > :rev)
```

### GraphQL Schema (`schema/`)

**Types (`ifc_types.py`)** -- mirrors the IFC 4.3 entity hierarchy:

| Type | Role |
|---|---|
| `IfcRoot` (interface) | `global_id`, `name`, `description` |
| `IfcObjectDefinition` (interface) | Extends IfcRoot |
| `IfcProduct` (type) | Main query return type. Adds `ifc_class`, `object_type`, `tag`, `contained_in`, `mesh`, `neighbors` |
| `IfcMeshRepresentation` | `vertices`, `normals`, `faces` as `Base64Bytes` |
| `IfcRelatedProduct` | Neighbor reference with `relationship` enum |
| `IfcSpatialContainerRef` | Spatial container reference |
| `IfcSpatialNode` | Recursive tree node with `children` + `contained_elements` |
| `Revision` | `id`, `label`, `ifc_filename`, `created_at` |
| `RevisionDiff` | `from_revision`, `to_revision`, `added[]`, `modified[]`, `deleted[]` |
| `RevisionDiffEntry` | `global_id`, `ifc_class`, `name`, `change_type` |
| `ChangeType` (enum) | `ADDED`, `MODIFIED`, `DELETED` |

**Enums (`ifc_enums.py`)**:

| Enum | Values |
|---|---|
| `IfcRelationshipType` | `REL_AGGREGATES`, `REL_CONTAINED_IN_SPATIAL`, `REL_CONNECTS_ELEMENTS`, `REL_VOIDS_ELEMENT`, `REL_FILLS_ELEMENT`, `REL_ASSOCIATES_MATERIAL`, `REL_DEFINES_BY_TYPE` |
| `IfcProductCategory` | `WALL`, `SLAB`, `BEAM`, `COLUMN`, `DOOR`, `WINDOW`, etc. (22 values) |

**Scalars (`scalars.py`)** -- `Base64Bytes`: serializes `bytes` as Base64 strings in GraphQL.

**Root Query (`queries.py`)** -- all fields accept optional `revision` (defaults to latest):

| Field | Args | Returns |
|---|---|---|
| `ifcProduct` | `globalId`, `revision?` | `IfcProduct?` |
| `ifcProducts` | `ifcClass?`, `containedIn?`, `revision?` | `[IfcProduct]` |
| `spatialTree` | `revision?` | `[IfcSpatialNode]` |
| `revisions` | (none) | `[Revision]` |
| `revisionDiff` | `fromRev`, `toRev` | `RevisionDiff` |

Key internal helpers in `queries.py`:
- `_resolve_revision(revision)` -- defaults `None` to `get_latest_revision_id()`
- `_row_to_product(row, rev)` -- enriches a DB dict with mesh, container ref, and graph neighbors
- `_dict_to_spatial_node(d)` -- recursively converts tree dicts to `IfcSpatialNode`

### IFC Services (`services/ifc/`)

**`geometry.py`** -- IFC mesh extraction:

| Export | Purpose |
|---|---|
| `IfcProductRecord` (dataclass) | Maps 1:1 to an `ifc_products` row. Fields: `global_id`, `ifc_class`, `name`, `description`, `object_type`, `tag`, `contained_in`, `vertices`, `normals`, `faces`, `matrix`, `content_hash` |
| `extract_products(ifc_path)` | Opens IFC file, returns list of `IfcProductRecord` |
| `extract_products_from_model(model)` | Same but accepts an already-opened `ifcopenshell.file` (avoids double-open) |

Internal functions: `_compute_content_hash(...)`, `_build_containment_map(model)`, `_extract_spatial_elements(model, map)`, `_extract_geometric_elements(model, map)`.

**`ingestion.py`** -- versioned two-phase ingestion pipeline:

| Export | Purpose |
|---|---|
| `ingest_ifc(ifc_path, label?)` | Main entry point. Returns `IngestionResult` |
| `IngestionResult` (dataclass) | `revision_id`, `total_products`, `added`, `modified`, `deleted`, `unchanged`, `edges_created` |
| `IfcRelationshipRecord` (dataclass) | `from_global_id`, `to_global_id`, `relationship_type` |

The pipeline:
1. Opens IFC model once, extracts products + relationships
2. Creates a `revisions` row (single relational transaction for steps 2-5)
3. Loads current `content_hash` values, diffs against new products
4. Closes SCD2 rows for modified/deleted products
5. Inserts new SCD2 rows for added/modified products
6. Closes graph nodes + edges for modified/deleted (best-effort)
7. Creates graph nodes for added/modified
8. Creates graph edges for relationships involving changed products

Relationships extracted: `IfcRelAggregates`, `IfcRelContainedInSpatialStructure`, `IfcRelVoidsElement`, `IfcRelFillsElement`, `IfcRelConnectsElements`.

### Graph Services (`services/graph/`)

**`age_client.py`** -- AGE Cypher executor with read and write operations:

| Function | Category | Purpose |
|---|---|---|
| `get_neighbors(global_id, rev)` | Read | Outgoing + incoming neighbors at revision |
| `get_spatial_tree_roots(rev)` | Read | IfcProject nodes at revision |
| `get_spatial_children(global_id, rev)` | Read | Children via IfcRelAggregates |
| `get_contained_elements(spatial_gid, rev)` | Read | Elements via IfcRelContainedInSpatialStructure |
| `build_spatial_tree(rev)` | Read | Full recursive tree from roots |
| `create_node(ifc_class, global_id, name, rev_id)` | Write | New revision-tagged node |
| `close_node(global_id, rev_id)` | Write | Set `valid_to_rev` on current node |
| `create_edge(from_gid, to_gid, rel_type, rev_id)` | Write | New revision-tagged edge |
| `close_edges_for_node(global_id, rev_id)` | Write | Close all edges for a node |

Internal helpers:
- `_rev_filter(alias, rev)` -- generates Cypher `WHERE` clause for revision visibility
- `_exec_cypher(cypher, cols)` -- read queries via AGE SQL interface
- `_exec_cypher_write(cypher)` -- write queries (must include `RETURN`)
- `_ensure_vlabel(label)` / `_ensure_elabel(label)` -- auto-creates AGE labels with caching
- `_validate_id(value)` -- validates GlobalIds for safe Cypher embedding
- `_validate_label(label)` -- validates IFC class names as AGE labels
- `_escape_cypher_string(value)` -- escapes strings for Cypher literals

**`queries.py`** -- Cypher templates using `str.format()` placeholders:
- `NEIGHBORS_OUT`, `NEIGHBORS_IN` -- neighbor traversal
- `SPATIAL_ROOTS` -- IfcProject nodes
- `SPATIAL_CHILDREN` -- decomposition children
- `CONTAINED_ELEMENTS` -- containment query

---

## Database Schema (`infra/init-age.sql`)

### Tables

**`revisions`** -- one row per IFC file upload:
- `id SERIAL PK`, `label TEXT`, `ifc_filename TEXT NOT NULL`, `created_at TIMESTAMPTZ`

**`ifc_products`** -- SCD Type 2 versioned product rows:
- `id SERIAL PK` (surrogate, multiple rows per `global_id`)
- IFC attributes: `global_id`, `ifc_class`, `name`, `description`, `object_type`, `tag`, `contained_in`
- Geometry BYTEAs: `vertices`, `normals`, `faces`, `matrix`
- Versioning: `content_hash TEXT NOT NULL`, `valid_from_rev INT NOT NULL FK`, `valid_to_rev INT FK`
- `UNIQUE(global_id, valid_from_rev)`

### Key Indexes
- `idx_ifc_products_current` -- `global_id WHERE valid_to_rev IS NULL`
- `idx_ifc_products_class` -- `(ifc_class, valid_to_rev)`
- `idx_ifc_products_contained` -- `contained_in WHERE valid_to_rev IS NULL`
- `idx_ifc_products_rev_range` -- `(valid_from_rev, valid_to_rev)`

### Graph (Apache AGE)

- Graph name: `bimatlas`
- Node labels: IFC class names (e.g. `IfcWall`, `IfcBuildingStorey`)
- Edge labels: IFC relationship names (e.g. `IfcRelAggregates`, `IfcRelContainedInSpatialStructure`)
- All nodes/edges carry: `valid_from_rev INT`, `valid_to_rev INT` (`-1` = current, AGE has no NULL props)
- Nodes carry: `global_id`, `name`

---

## Frontend (`apps/web/src/`)

### Routing
- **`+layout.svelte`** -- root layout
- **`+page.svelte`** -- main app page with 3D View / Graph toggle tabs

### Key Libraries (`lib/`)

| Module | File(s) | Purpose |
|---|---|---|
| `engine/` | `SceneManager.ts`, `BufferGeometryLoader.ts` | Three.js lifecycle, mesh registry, highlight, camera. `BufferGeometryLoader` decodes Base64 to `THREE.BufferGeometry` |
| `graph/` | `ForceGraph.svelte`, `graphStore.svelte.ts` | 3d-force-graph wrapper. Node clicks sync to shared selection state |
| `ui/` | `Viewport.svelte`, `SelectionPanel.svelte` | Viewport accepts `{overlay?, toolbar?}` Snippet props for extensibility |
| `state/` | `selection.svelte.ts` | Shared reactive state using Svelte 5 `$state` runes: `getSelection()` (activeGlobalId), `getRevisionState()` (activeRevision) |
| `api/` | `client.ts` | urql GraphQL client pointing at `/graphql` |

### Conventions
- **Svelte 5 runes only** -- use `$state`, `$derived`, `$effect`, `$props`. No legacy `$:` or stores.
- **Snippet extensibility** -- `Viewport.svelte` accepts `Snippet` typed props (`overlay`, `toolbar`) via `{@render}`.
- **State access pattern** -- `getSelection()` / `getRevisionState()` return getter/setter objects importable from both `.svelte` and `.ts` files.

---

## Core Patterns & Conventions

### Versioning (SCD Type 2)
- Every IFC upload creates a `revisions` row.
- Only changed products get new `ifc_products` rows (detected via `content_hash`).
- Unchanged products carry forward via open `valid_to_rev IS NULL` window.
- Graph mirrors this with `valid_from_rev`/`valid_to_rev` on every node and edge.
- All queries accept optional `revision` param; default = latest.
- `revision_diff` computes added/modified/deleted between any two revisions.

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
