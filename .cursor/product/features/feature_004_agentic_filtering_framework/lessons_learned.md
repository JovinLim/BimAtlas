# Hard Constraints

- All IDs (project_id, branch_id, revision_id, filter_set_id) are UUID strings; all new code must treat IDs as strings and query attributes via JSONB operators.
- IFC geometry is stored as a single `geometry BYTEA` blob on `ifc_entity`; MCP tools and agent must never expose or process geometry data.
- The `inherits_from` class operator depends on `get_descendants()` which loads IFC hierarchy from `validation_rule` via `fetch_validation_rules`. If the schema is not seeded, `inherits_from` returns no matches. Tests using `inherits_from` must use the `ifc_schema_seeded` fixture.
- LLM API keys can be stored in the `ifc_entity` attributes (IfcAgent) as part of the agent config. The frontend can also provide keys per-session without persisting them.
- MCP tools must wrap existing DB functions (db.py), not duplicate their logic. The filter engine, operator validation, and JSONB translation are already implemented.
- Nested JSONB key filtering uses a recursive JSONB walk in SQL; attribute keys can target keys at any depth (e.g., `PropertySets.PsetWallCommon.FireRating`).
- Inter-set `combination_logic` for applying multiple filter sets is always `"OR"`. `"AND"` combination of multiple filter sets is disabled. The agent must always pass `combination_logic="OR"` to `apply_filter_set_to_context`.
- All frontend Svelte components must follow `.cursor/rules/style.md` for HTML structure, layout (Flexbox/Grid, `gap`), CSS design tokens (`--color-bg-*`, `--color-text-*`, `--color-border-*`, `--color-brand-*`), and the BimAtlas dark color scheme.

# Resolved Pitfalls

- The agent chat was initially implemented as a sidebar panel in the main page. This caused layout issues and deviated from the popup-tab pattern used by Graph/Search/Table/Attributes. Converting to a popup with BroadcastChannel (request-context/context) resolved context sync issues and follows the established pattern.
- Chat history was initially sent from the frontend as a `chatHistory` array. This approach loses history on page reload and doesn't persist across sessions. Switching to DB-persisted `agent_chat` + `agent_chat_message` tables with a `chatId` parameter allows the backend to load prior messages and save new ones, maintaining full conversation context across sessions.
- LlamaIndex `ReActAgent.from_tools(..., chat_history=prior_messages)` accepts a list of `ChatMessage` objects for replay. The backend converts DB-stored messages to this format, providing seamless history continuation without changing the agent architecture.
- Pre-prompt was ignored by some custom/OpenAI-compatible providers. Duplicating the instruction in both system prompt (as "Runtime Instruction Override") and user message via `_compose_user_message` ensures reliable behavior across weak providers.
- AgentStream.delta was stripped before emitting; that removed inter-token whitespace and produced run-together text. Emitting raw delta preserves spacing and newlines.
- Each thinking chunk was rendered as a list item, fragmenting output. Joining chunks into a single block with `white-space: pre-wrap` displays streaming reasoning as readable text.
- Agent metadata showed only "Processing..." until completion. Using `handler.stream_events()` and emitting AgentStream.delta, ToolCall, ToolCallResult progressively streams actual reasoning and tool calls in real time.
- Page refresh during an in-flight response lost state. Adding `LiveChatStreamManager`, GET `/agent/chats/{id}/live-state` and `/live-stream`, and frontend reconnect logic allows resuming and continuing to receive events after refresh.
