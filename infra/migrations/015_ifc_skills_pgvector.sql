-- Migration 015: IFC skills table with pgvector for semantic search
--
-- Stores learned IFC semantic mappings (relational paths, filter modes) scoped
-- by project_id and optional branch_id. Embeddings enable cosine similarity
-- search via search_skills(intent).
--
-- Requires: pgvector extension. If using Apache AGE image, ensure pgvector
-- is installed or use a Postgres image with both AGE and pgvector.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS ifc_skill (
    skill_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id  UUID NOT NULL REFERENCES project(project_id) ON DELETE CASCADE,
    branch_id   UUID REFERENCES branch(branch_id) ON DELETE CASCADE,
    title       VARCHAR NOT NULL,
    intent      TEXT NOT NULL,
    frontmatter JSONB NOT NULL DEFAULT '{}',
    content_md  TEXT NOT NULL DEFAULT '',
    embedding   vector(1536),
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ifc_skill_project ON ifc_skill (project_id);
CREATE INDEX IF NOT EXISTS idx_ifc_skill_branch ON ifc_skill (branch_id);
CREATE INDEX IF NOT EXISTS idx_ifc_skill_project_branch ON ifc_skill (project_id, branch_id);

-- HNSW index for approximate nearest-neighbor cosine search
CREATE INDEX IF NOT EXISTS idx_ifc_skill_embedding_hnsw
    ON ifc_skill USING hnsw (embedding vector_cosine_ops)
    WHERE embedding IS NOT NULL;
