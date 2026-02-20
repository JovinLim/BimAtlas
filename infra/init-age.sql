-- BimAtlas: Bootstrap Apache AGE extension and versioned relational schema.

CREATE EXTENSION IF NOT EXISTS age;
LOAD 'age';
SET search_path = ag_catalog, "$user", public;
SELECT create_graph('bimatlas');

-- ============================================================================
-- Projects
-- ============================================================================

CREATE TABLE IF NOT EXISTS projects (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- ============================================================================
-- Branches (each project has at least a "main" branch)
-- ============================================================================

CREATE TABLE IF NOT EXISTS branches (
    id          SERIAL PRIMARY KEY,
    project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name        TEXT NOT NULL DEFAULT 'main',
    created_at  TIMESTAMPTZ DEFAULT now(),

    UNIQUE (project_id, name)
);

CREATE INDEX idx_branches_project ON branches (project_id);

-- ============================================================================
-- Revision tracking (scoped to a branch)
-- ============================================================================

CREATE TABLE IF NOT EXISTS revisions (
    id          SERIAL PRIMARY KEY,
    branch_id   INTEGER NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
    label       TEXT,                       -- User-defined label, e.g. "v2.1 - structural update"
    ifc_filename TEXT NOT NULL,             -- Original filename for reference
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_revisions_branch ON revisions (branch_id);

-- ============================================================================
-- SCD Type 2 versioned product table (scoped to a branch)
-- ============================================================================
-- Each IFC file upload creates a revision on a branch. Products use Slowly
-- Changing Dimension Type 2: only changed/added products get new rows (detected
-- via content_hash); unchanged products carry forward implicitly via their open
-- valid_to_rev IS NULL window.  Products are scoped per-branch so each branch
-- has an independent version history.

CREATE TABLE IF NOT EXISTS ifc_products (
    id              SERIAL PRIMARY KEY,         -- Surrogate PK (multiple rows per global_id)
    branch_id       INTEGER NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
    global_id       TEXT NOT NULL,              -- IfcRoot.GlobalId (stable across revisions)
    ifc_class       TEXT NOT NULL,              -- Runtime entity, e.g. "IfcWall"
    name            TEXT,                       -- IfcRoot.Name
    description     TEXT,                       -- IfcRoot.Description
    object_type     TEXT,                       -- IfcObject.ObjectType
    tag             TEXT,                       -- IfcElement.Tag
    contained_in    TEXT,                       -- GlobalId of spatial container (IFC 4.3 sec 4.1.5.13)
    vertices        BYTEA,
    normals         BYTEA,
    faces           BYTEA,
    matrix          BYTEA,
    content_hash    TEXT NOT NULL,              -- SHA-256 for change detection
    valid_from_rev  INTEGER NOT NULL REFERENCES revisions(id),  -- Revision that introduced this row
    valid_to_rev    INTEGER REFERENCES revisions(id),           -- NULL = current; set when superseded/deleted

    UNIQUE (branch_id, global_id, valid_from_rev)
);

-- Indexes for efficient querying
CREATE INDEX idx_ifc_products_current    ON ifc_products (branch_id, global_id) WHERE valid_to_rev IS NULL;
CREATE INDEX idx_ifc_products_class      ON ifc_products (branch_id, ifc_class, valid_to_rev);
CREATE INDEX idx_ifc_products_contained  ON ifc_products (branch_id, contained_in) WHERE valid_to_rev IS NULL;
CREATE INDEX idx_ifc_products_rev_range  ON ifc_products (branch_id, valid_from_rev, valid_to_rev);

-- ============================================================================
-- Filter sets (named, reusable filter collections scoped to a branch)
-- ============================================================================

CREATE TABLE IF NOT EXISTS filter_sets (
    id          SERIAL PRIMARY KEY,
    branch_id   INTEGER NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    logic       TEXT NOT NULL DEFAULT 'AND' CHECK (logic IN ('AND', 'OR')),
    filters     JSONB NOT NULL DEFAULT '[]',
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_filter_sets_branch ON filter_sets (branch_id);

-- ============================================================================
-- Applied filter sets per branch (tracks which sets are currently active)
-- ============================================================================

CREATE TABLE IF NOT EXISTS branch_applied_filter_sets (
    branch_id       INTEGER NOT NULL REFERENCES branches(id) ON DELETE CASCADE,
    filter_set_id   INTEGER NOT NULL REFERENCES filter_sets(id) ON DELETE CASCADE,
    combination_logic TEXT NOT NULL DEFAULT 'AND' CHECK (combination_logic IN ('AND', 'OR')),
    applied_at      TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (branch_id, filter_set_id)
);
