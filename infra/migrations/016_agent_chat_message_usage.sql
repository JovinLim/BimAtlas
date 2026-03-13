-- Add token usage (and optional cost) to agent chat messages.
-- Idempotent — safe to re-run.

ALTER TABLE agent_chat_message
ADD COLUMN IF NOT EXISTS usage JSONB;
