-- FEAT-004: Refactor agents from agent_config table to ifc_entity (IfcAgent).
-- Agents are stored as ifc_entity rows with ifc_class='IfcAgent' and attributes
-- {name, provider, model, api_key, base_url, pre_prompt}. agent_chat and agent_chat_message
-- remain unchanged and continue to work with the agent workflow.

DROP TABLE IF EXISTS agent_config;
