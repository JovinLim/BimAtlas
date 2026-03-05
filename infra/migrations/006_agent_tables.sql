-- FEAT-004: Agent configurations and chat history tables.
-- Idempotent — safe to re-run on databases that already have these tables.

-- Agent configurations (IfcAgent saved LLM models, project-scoped)
CREATE TABLE IF NOT EXISTS agent_config (
    agent_config_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL REFERENCES project(project_id) ON DELETE CASCADE,
    name            VARCHAR NOT NULL,
    provider        VARCHAR NOT NULL,
    model           VARCHAR NOT NULL,
    api_key         VARCHAR NOT NULL DEFAULT '',
    base_url        VARCHAR,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_config_project ON agent_config (project_id);

-- Agent chat sessions (persistent conversation history)
CREATE TABLE IF NOT EXISTS agent_chat (
    chat_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES project(project_id) ON DELETE CASCADE,
    branch_id  UUID NOT NULL REFERENCES branch(branch_id) ON DELETE CASCADE,
    title      VARCHAR NOT NULL DEFAULT 'New chat',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_chat_project ON agent_chat (project_id);
CREATE INDEX IF NOT EXISTS idx_agent_chat_branch  ON agent_chat (branch_id);

-- Agent chat messages
CREATE TABLE IF NOT EXISTS agent_chat_message (
    message_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id    UUID NOT NULL REFERENCES agent_chat(chat_id) ON DELETE CASCADE,
    role       VARCHAR NOT NULL,
    content    TEXT NOT NULL DEFAULT '',
    tool_calls JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_chat_message_chat ON agent_chat_message (chat_id, created_at);
