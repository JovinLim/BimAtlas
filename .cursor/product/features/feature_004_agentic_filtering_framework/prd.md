---
feature_id: "FEAT-004"
status: "implemented"
priority: "high"
---

# Feature: Agentic Filtering Framework (Direct API + IFC Skill Guardrails)

## 1. Problem Statement

Users need the ability to perform complex data audits and visualization queries on IFC models using natural language. Today, constructing multi-condition filter sets requires manual selection of IFC classes, operators, and values through a structured UI. Domain experts (architects, MEP engineers, structural engineers) should be able to describe their intent in plain language — e.g., "Show me all entities whose IFC class inherits from IfcWindow" or "Filter for fire-rated walls with rating above 2 hours" — and have an AI agent translate that into the correct sequence of filter operations.

The architecture uses **programmatic API tools** (execute_request, discover_api, search_skills, etc.) orchestrated by a **LlamaIndex** agent—no MCP; tools are native LlamaIndex FunctionTools. A **domain-safe execution policy** enforces search-before-create: the agent searches pgvector-backed IFC skills first, reads the discover_api cheat-sheet, escalates via ask_user_for_guidance on ambiguity, and saves new mappings via save_ifc_skill.

## 2. Core Requirements

### Req 1 (Tool Layer — Implemented)

The backend exposes these tools:

1. **`discover_api`** — Returns curated OpenAPI + GraphQL spec with IFC cheat-sheet (relational paths, filter modes, operators, examples). Grounds the LLM in real API structure.
2. **`execute_request`** — Makes HTTP requests (GET/POST/PUT/DELETE) to the BimAtlas API server-side. Responses truncated to avoid context overflow. Supports GraphQL and REST.
3. **`search_skills`** — Semantic search over pgvector-backed `ifc_skill` table. Returns frontmatter for matching intent. Scoped by project_id and optional branch_id.
4. **`ask_user_for_guidance`** — Escalates when the agent lacks knowledge or encounters ambiguity. Emits `guidance_request` SSE event; frontend pauses turn for user reply.
5. **`save_ifc_skill`** — Persists newly learned IFC mappings (title, intent, frontmatter, content_md) with embedding for future semantic search.
6. **`list_uploaded_files`** / **`read_uploaded_file`** — Session file management for user-uploaded PDFs, CSVs, etc.

### Req 2 (LlamaIndex Agent Orchestration)

- The agent must follow a **domain-safe workflow**: search_skills → discover_api → execute_request → save_ifc_skill on success.
- The agent must call `search_skills` first for complex filter intent before constructing GraphQL.
- The agent must read the discover_api `ifc_cheat_sheet` before building requests.
- The agent must call `ask_user_for_guidance` immediately on ambiguity (no guessing).
- The agent must call `save_ifc_skill` after successful user-guided resolution.
- The `inherits_from` operator is supported via backend `get_descendants()` IFC hierarchy logic.

### Req 3 (Frontend Chat Interface)

- A Svelte chat panel in a **popup browser tab** (following the Graph/Search/Table/Attributes popup convention with BroadcastChannel context sync).
- A model configuration sub-panel: Provider (OpenAI, Anthropic, Google, Ollama, Custom), Model name, API Key. Configuration is persisted to localStorage for convenience.
- **IfcAgent saved models**: Users can save LLM configurations as named "IfcAgent" entities (project-scoped, stored as `ifc_entity` rows with `ifc_class='IfcAgent'` and attributes `{name, provider, model, api_key, base_url}`). Saved agents can be selected, updated, or deleted. IfcAgent entities do not have geometry and are not rendered in the 3D viewer.
- Chat messages must show tool-call activity (which API tools were invoked, with what arguments) for transparency.
- Errors from the agent (LLM failures, tool errors, network issues) must be visually distinguished in the chat with error styling.

### Req 6 (Persistent Chat History)

- Chat conversations are persisted in the database (`agent_chat` + `agent_chat_message` tables).
- Users can have multiple chat sessions per project/branch.
- Users can create new chats, switch between existing chats, rename, and delete chats.
- When sending a message, the backend loads prior messages from the chat's DB history and replays them to the LlamaIndex agent for context continuity.
- The assistant's response (including tool calls) is saved back to the chat after completion.

### Req 4 (State Synchronization)

- When the agent applies filter sets via `execute_request` (GraphQL mutation or REST), the backend emits `apply_filter_sets` on `/stream/agent-events`. The frontend re-fetches the product stream to reflect the new filter state.
- When the agent calls `ask_user_for_guidance`, the backend emits a dedicated `guidance_request` SSE event with question/context. The frontend renders the guidance prominently and keeps the turn open for user reply.

### Req 5 (Filtering Engine Completeness)

The full operator vocabulary from FEAT-001 must be available to the agent:

- **String/Logical:** `is`, `is_not`, `contains`, `not_contains`, `starts_with`, `ends_with`, `is_empty`, `is_not_empty`
- **Numeric:** `equals`, `not_equals`, `gt`, `lt`, `gte`, `lte`
- **IFC Structural:** `inherits_from` (recursive class + descendants)

## 3. Out of Scope (Strict Constraints)

- Do not build a general-purpose chat assistant. The agent's sole purpose is filter construction and application on IFC data.
- LLM API keys may be stored in the `ifc_entity` attributes (as part of IfcAgent saved models). They can also be provided per-session without persistence.
- Do not modify the existing filter set CRUD or JSONB schema — the agent uses execute_request to call existing GraphQL mutations.
- Do not implement graph traversal via Cypher for filtering; use the existing relational JSONB filter engine. The agent constructs GraphQL queries that hit the backend filter engine.
- Do not expose geometry (BYTEA) data to the LLM or through API tools.
- Do not require a specific LLM provider; the system must be provider-agnostic (OpenAI, Anthropic, Google, Ollama, etc.).
- Inter-set `combination_logic` for applying multiple filter sets to the same context is always `"OR"`. `"AND"` combination is disabled for now.
- All frontend UI must follow `.cursor/rules/style.md` for HTML structure, layout conventions, CSS tokens, and the BimAtlas color scheme.

## 4. Success Criteria

- [x] `discover_api` returns curated API spec with IFC cheat-sheet.
- [x] `execute_request` makes HTTP requests to BimAtlas API with truncation and endpoint enforcement.
- [x] `search_skills` performs semantic search over pgvector-backed ifc_skill table.
- [x] `ask_user_for_guidance` emits `guidance_request` SSE; frontend renders and pauses for user reply.
- [x] `save_ifc_skill` persists new IFC mappings with embedding for future search.
- [x] A natural language query like "Filter for entities whose class inherits from IfcWindow" results in correct filter application via the domain-safe flow.
- [x] The Svelte chat interface streams agent responses and shows tool-call activity.
- [x] The model configuration panel allows switching providers and models without backend changes.
- [x] Applied filters from the agent are reflected in the 3D viewer and search state within 2 seconds.

## 5. Architecture Overview

```
┌─────────────┐     Chat message      ┌──────────────────────────────────────┐
│  Svelte UI  │ ───────────────────►  │  FastAPI Backend                     │
│  Chat Panel │ ◄─────────────────── │  POST /agent/chat                    │
│  + Config   │   SSE stream / resp   │                                      │
└─────────────┘   (guidance_request)  │  ┌────────────────────────────────┐ │
       ▲                              │  │ LlamaIndex Agent (Workflow)     │ │
       │ State sync                   │  │  search_skills → discover_api   │ │
       │ (BroadcastChannel            │  │  → execute_request              │ │
       │  /stream/agent-events)       │  │  ask_user_for_guidance on gap   │ │
       ▼                              │  │  save_ifc_skill on success     │ │
┌─────────────┐                       │  └────────┬───────────────────────┘ │
│  Search     │                       │           │                         │
│  State +    │                       │  ┌────────▼───────────────────────┐ │
│  3D Viewer  │                       │  │  Tools: discover_api,         │ │
└─────────────┘                       │  │  execute_request, search_skills│ │
                                      │  │  ask_user_for_guidance,        │ │
                                      │  │  save_ifc_skill                │ │
                                      │  └────────┬───────────────────────┘ │
                                      │  ┌────────▼─────────┐                │
                                      │  │  DB + pgvector   │                │
                                      │  │  (ifc_skill)     │                │
                                      │  └──────────────────┘                │
                                      └──────────────────────────────────────┘
```

## 6. Key Dependencies

- **LlamaIndex** (`llama-index-core`, `llama-index-llms-openai`, `llama-index-llms-anthropic`, `llama-index-llms-google`, `llama-index-llms-ollama`)
- **httpx** for execute_request server-side HTTP calls
- **pgvector** for ifc_skill semantic search (migration 015)
- Existing FEAT-001 filter engine (db.py, filter_operators.py, queries.py)
- Existing IFC schema loader (ifc_schema_loader.py, ifc_4_3_schema.json)
