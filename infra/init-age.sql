-- BimAtlas: Bootstrap Apache AGE extension and versioned relational schema.
-- Relational tables, enums, and indexes are created first so they exist
-- even if AGE graph creation fails.

-- ============================================================================
-- Enums
-- ============================================================================

CREATE TYPE merge_status AS ENUM (
    'Draft', 'Previewing', 'Conflict', 'Ready', 'Merged', 'Closed'
);

CREATE TYPE conflict_type AS ENUM (
    'Attribute_Mismatch', 'Geometry_Mismatch',
    'Topology_Mismatch', 'Deleted_vs_Modified'
);

CREATE TYPE resolution_status AS ENUM (
    'Unresolved', 'Source_Wins', 'Target_Wins', 'Manual_Merge'
);

CREATE TYPE rule_severity AS ENUM ('Error', 'Warning', 'Info');

CREATE TYPE logic_operator AS ENUM ('AND', 'OR');

-- ============================================================================
-- IFC Schema Registry
-- ============================================================================

CREATE TABLE IF NOT EXISTS ifc_schema (
    schema_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version_name VARCHAR NOT NULL UNIQUE
);

-- ============================================================================
-- Projects
-- ============================================================================

CREATE TABLE IF NOT EXISTS project (
    project_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name         VARCHAR NOT NULL,
    description  TEXT,
    created_at   TIMESTAMPTZ DEFAULT now()
);

-- Junction: a project can have multiple IFC schemas applied
CREATE TABLE IF NOT EXISTS project_schema (
    project_id UUID NOT NULL REFERENCES project(project_id) ON DELETE CASCADE,
    schema_id  UUID NOT NULL REFERENCES ifc_schema(schema_id) ON DELETE CASCADE,
    PRIMARY KEY (project_id, schema_id)
);

-- ============================================================================
-- Branches (each project has at least a "main" branch)
-- ============================================================================

CREATE TABLE IF NOT EXISTS branch (
    branch_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id  UUID NOT NULL REFERENCES project(project_id) ON DELETE CASCADE,
    name        VARCHAR NOT NULL DEFAULT 'main',
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ DEFAULT now(),

    UNIQUE (project_id, name)
);

CREATE INDEX idx_branch_project ON branch (project_id);

-- ============================================================================
-- Revisions (scoped to a branch)
-- ============================================================================
-- revision_seq is a global monotonic SERIAL used for SCD Type 2 temporal
-- ordering. UUID PKs are not temporally sortable, so revision_seq provides
-- efficient integer comparison for range queries and AGE graph properties.

CREATE TABLE IF NOT EXISTS revision (
    revision_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    branch_id          UUID NOT NULL REFERENCES branch(branch_id) ON DELETE CASCADE,
    revision_seq       SERIAL NOT NULL,
    parent_revision_id UUID REFERENCES revision(revision_id),
    ifc_filename       TEXT,
    author_id          VARCHAR,
    commit_message     TEXT,
    created_at         TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_revision_branch ON revision (branch_id);
CREATE INDEX idx_revision_seq    ON revision (branch_id, revision_seq);

-- ============================================================================
-- SCD Type 2 versioned entity table (scoped to a branch)
-- ============================================================================
-- Each IFC file upload creates a revision on a branch. Entities use Slowly
-- Changing Dimension Type 2: only changed/added entities get new rows
-- (detected via content_hash); unchanged entities carry forward implicitly
-- via their open obsoleted_in_revision_id IS NULL window. Entities are
-- scoped per-branch so each branch has an independent version history.
--
-- IFC attributes (Name, Description, ObjectType, Tag, ContainedIn, etc.)
-- are stored in the JSONB `attributes` column. Geometry data (vertices,
-- normals, faces, matrix) is packed into a single `geometry` BYTEA blob.

CREATE TABLE IF NOT EXISTS ifc_entity (
    entity_id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    branch_id                UUID NOT NULL REFERENCES branch(branch_id) ON DELETE CASCADE,
    ifc_global_id            VARCHAR NOT NULL,
    ifc_class                VARCHAR NOT NULL,
    attributes               JSONB NOT NULL DEFAULT '{}',
    geometry                 BYTEA,
    content_hash             TEXT NOT NULL,
    created_in_revision_id   UUID NOT NULL REFERENCES revision(revision_id),
    obsoleted_in_revision_id UUID REFERENCES revision(revision_id),

    UNIQUE (branch_id, ifc_global_id, created_in_revision_id)
);

CREATE INDEX idx_ifc_entity_current    ON ifc_entity (branch_id, ifc_global_id) WHERE obsoleted_in_revision_id IS NULL;
CREATE INDEX idx_ifc_entity_class      ON ifc_entity (branch_id, ifc_class) WHERE obsoleted_in_revision_id IS NULL;
CREATE INDEX idx_ifc_entity_rev_range  ON ifc_entity (branch_id, created_in_revision_id, obsoleted_in_revision_id);

-- GIN index for JSONB attribute queries (FEAT-001 dynamic filter sets)
CREATE INDEX idx_ifc_entity_attributes ON ifc_entity USING GIN (attributes);

-- ============================================================================
-- Filter sets (named, reusable filter collections scoped to a branch)
-- ============================================================================

CREATE TABLE IF NOT EXISTS filter_sets (
    filter_set_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    branch_id     UUID NOT NULL REFERENCES branch(branch_id) ON DELETE CASCADE,
    name          VARCHAR NOT NULL,
    logic         logic_operator NOT NULL DEFAULT 'AND',
    filters       JSONB NOT NULL DEFAULT '[]',
    color         VARCHAR NOT NULL DEFAULT '#4A90D9',
    created_at    TIMESTAMPTZ DEFAULT now(),
    updated_at    TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_filter_sets_branch ON filter_sets (branch_id);

-- ============================================================================
-- Sheet templates (project-scoped bottom-sheet table state for /table page)
-- ============================================================================

CREATE TABLE IF NOT EXISTS sheet_template (
    sheet_template_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id        UUID NOT NULL REFERENCES project(project_id) ON DELETE CASCADE,
    name              VARCHAR NOT NULL,
    sheet             JSONB NOT NULL DEFAULT '{}',
    open              BOOLEAN NOT NULL DEFAULT FALSE,
    created_at        TIMESTAMPTZ DEFAULT now(),
    updated_at        TIMESTAMPTZ DEFAULT now(),
    UNIQUE (project_id, name)
);

CREATE INDEX idx_sheet_template_project ON sheet_template (project_id);

-- ============================================================================
-- Applied filter sets per branch (tracks which sets are currently active)
-- ============================================================================

CREATE TABLE IF NOT EXISTS branch_applied_filter_sets (
    branch_id         UUID NOT NULL REFERENCES branch(branch_id) ON DELETE CASCADE,
    filter_set_id     UUID NOT NULL REFERENCES filter_sets(filter_set_id) ON DELETE CASCADE,
    combination_logic logic_operator NOT NULL DEFAULT 'AND',
    display_order     INTEGER NOT NULL DEFAULT 0,
    applied_at        TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (branch_id, filter_set_id)
);

-- ============================================================================
-- Merge requests & conflict resolution
-- ============================================================================

CREATE TABLE IF NOT EXISTS merge_request (
    merge_request_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id       UUID NOT NULL REFERENCES project(project_id) ON DELETE CASCADE,
    source_branch_id UUID NOT NULL REFERENCES branch(branch_id),
    target_branch_id UUID NOT NULL REFERENCES branch(branch_id),
    status           merge_status NOT NULL DEFAULT 'Draft',
    created_by       VARCHAR,
    created_at       TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS merge_conflict_log (
    log_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    merge_request_id  UUID NOT NULL REFERENCES merge_request(merge_request_id) ON DELETE CASCADE,
    ifc_global_id     VARCHAR NOT NULL,
    source_entity_id  UUID REFERENCES ifc_entity(entity_id),
    target_entity_id  UUID REFERENCES ifc_entity(entity_id),
    conflict_type     conflict_type NOT NULL,
    resolution_status resolution_status NOT NULL DEFAULT 'Unresolved',
    resolved_entity_id UUID REFERENCES ifc_entity(entity_id)
);

-- ============================================================================
-- Validation rules
-- ============================================================================

CREATE TABLE IF NOT EXISTS validation_rule (
    rule_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name             VARCHAR NOT NULL,
    description      TEXT,
    schema_id        UUID REFERENCES ifc_schema(schema_id) ON DELETE CASCADE,
    project_id       UUID REFERENCES project(project_id),
    target_ifc_class VARCHAR NOT NULL,
    rule_schema      JSONB NOT NULL,
    severity         rule_severity NOT NULL DEFAULT 'Error',
    is_active        BOOLEAN NOT NULL DEFAULT TRUE
);

-- ============================================================================
-- Agent chat sessions (persistent conversation history)
-- ============================================================================
-- Note: Agent configs (IfcAgent) are stored as ifc_entity rows with
-- ifc_class='IfcAgent' and attributes {name, provider, model, api_key, base_url}.
-- ============================================================================

CREATE TABLE IF NOT EXISTS agent_chat (
    chat_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES project(project_id) ON DELETE CASCADE,
    branch_id  UUID NOT NULL REFERENCES branch(branch_id) ON DELETE CASCADE,
    title      VARCHAR NOT NULL DEFAULT 'New chat',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_agent_chat_project ON agent_chat (project_id);
CREATE INDEX idx_agent_chat_branch  ON agent_chat (branch_id);

CREATE TABLE IF NOT EXISTS agent_chat_message (
    message_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id    UUID NOT NULL REFERENCES agent_chat(chat_id) ON DELETE CASCADE,
    role       VARCHAR NOT NULL,
    content    TEXT NOT NULL DEFAULT '',
    tool_calls JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_agent_chat_message_chat ON agent_chat_message (chat_id, created_at);

-- ============================================================================
-- Apache AGE extension and graph (after relational schema)
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS age;
LOAD 'age';
SET search_path = ag_catalog, "$user", public;
SELECT create_graph('bimatlas');
