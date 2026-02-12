-- BimAtlas: Bootstrap Apache AGE extension and versioned relational schema.

CREATE EXTENSION IF NOT EXISTS age;
LOAD 'age';
SET search_path = ag_catalog, "$user", public;
SELECT create_graph('bimatlas');

-- ============================================================================
-- Revision tracking
-- ============================================================================

CREATE TABLE IF NOT EXISTS revisions (
    id          SERIAL PRIMARY KEY,
    label       TEXT,                       -- User-defined label, e.g. "v2.1 - structural update"
    ifc_filename TEXT NOT NULL,             -- Original filename for reference
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- ============================================================================
-- SCD Type 2 versioned product table
-- ============================================================================
-- Each IFC file upload creates a revision. Products use Slowly Changing
-- Dimension Type 2: only changed/added products get new rows (detected via
-- content_hash); unchanged products carry forward implicitly via their open
-- valid_to_rev IS NULL window.

CREATE TABLE IF NOT EXISTS ifc_products (
    id              SERIAL PRIMARY KEY,         -- Surrogate PK (multiple rows per global_id)
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

    UNIQUE (global_id, valid_from_rev)
);

-- Indexes for efficient querying
CREATE INDEX idx_ifc_products_current    ON ifc_products (global_id) WHERE valid_to_rev IS NULL;
CREATE INDEX idx_ifc_products_class      ON ifc_products (ifc_class, valid_to_rev);
CREATE INDEX idx_ifc_products_contained  ON ifc_products (contained_in) WHERE valid_to_rev IS NULL;
CREATE INDEX idx_ifc_products_rev_range  ON ifc_products (valid_from_rev, valid_to_rev);
