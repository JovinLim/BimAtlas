---
feature_id: "FEAT-004"
status: "draft"
priority: "high"
---

# Feature: Agentic Filtering Framework (MCP + LlamaIndex)

## 1. Problem Statement

Users need the ability to perform complex data audits and visualization queries on IFC models using natural language. Today, constructing multi-condition filter sets requires manual selection of IFC classes, operators, and values through a structured UI. Domain experts (architects, MEP engineers, structural engineers) should be able to describe their intent in plain language — e.g., "Show me all entities whose IFC class inherits from IfcWindow" or "Filter for fire-rated walls with rating above 2 hours" — and have an AI agent translate that into the correct sequence of filter operations.

The architecture must use the **Model Context Protocol (MCP)** to expose backend IFC functions as tools, orchestrated by a **LlamaIndex** agent that reasons over the project schema, constructs filter sets, and applies them to the active view.

## 2. Core Requirements

### Req 1 (MCP Tool Layer)

The backend must expose four MCP-compliant tools:

1. **`get_project_schema`** — Returns unique existing IFC classes, attributes, and relationships in the current project/branch/revision context. This grounds the LLM's choices in real data rather than hallucinated class names.
2. **`create_filter_set`** — Initializes a new named container (filter set) for a collection of filter conditions. Wraps the existing `create_filter_set` DB function.
3. **`add_filter_condition`** — Appends a specific logic rule (mode, key, operator, value) to an existing filter set. Wraps `update_filter_set` to append filters to the JSONB array.
4. **`apply_filter_set_to_context`** — Executes the filter set against a specific Project/Branch and updates the active view. Wraps `apply_filter_sets` and triggers a frontend notification.

### Req 2 (LlamaIndex Agent Orchestration)

- The agent must be orchestrated using LlamaIndex with a multi-step workflow: **Discovery → Validation → Creation → Application**.
- The agent must call `get_project_schema` first to ground its reasoning in real data before creating filters.
- The agent must validate that IFC classes, attributes, and operators exist in the schema before using them.
- The `inherits_from` operator must be supported, leveraging the backend's existing `get_descendants()` IFC hierarchy logic.

### Req 3 (Frontend Chat Interface)

- A Svelte chat panel with streaming LLM responses.
- A model configuration sub-panel: Provider (OpenAI, Anthropic, Google, Ollama, Custom), Model name, API Key (stored in browser localStorage, never sent to backend storage).
- Chat messages must show tool-call activity (which MCP tools were invoked, with what arguments) for transparency.
- The chat must be accessible from the main page (e.g., sidebar panel or popup tab following existing popup conventions).

### Req 4 (State Synchronization)

- When the agent applies a filter set via `apply_filter_set_to_context`, the backend must notify the Svelte frontend that filters have changed.
- The frontend must reactively re-fetch the product stream to reflect the new filter state.
- Mechanism: Server-Sent Events (SSE) on a dedicated `/stream/agent-events` endpoint, or a WebSocket channel, or a polling approach triggered by the chat response.

### Req 5 (Filtering Engine Completeness)

The full operator vocabulary from FEAT-001 must be available to the agent:

- **String/Logical:** `is`, `is_not`, `contains`, `not_contains`, `starts_with`, `ends_with`, `is_empty`, `is_not_empty`
- **Numeric:** `equals`, `not_equals`, `gt`, `lt`, `gte`, `lte`
- **IFC Structural:** `inherits_from` (recursive class + descendants)

## 3. Out of Scope (Strict Constraints)

- Do not build a general-purpose chat assistant. The agent's sole purpose is filter construction and application on IFC data.
- Do not store LLM API keys on the backend or in the database. Keys are provided per-session from the frontend.
- Do not modify the existing filter set CRUD or JSONB schema — the MCP tools must wrap existing functions.
- Do not implement graph traversal via Cypher for filtering; use the existing relational JSONB filter engine.
- Do not expose geometry (BYTEA) data to the LLM or through MCP tools.
- Do not require a specific LLM provider; the system must be provider-agnostic (OpenAI, Anthropic, Google, Ollama, etc.).
- Inter-set `combination_logic` for applying multiple filter sets to the same context is always `"OR"`. `"AND"` combination is disabled for now.
- All frontend UI must follow `.cursor/rules/style.md` for HTML structure, layout conventions, CSS tokens, and the BimAtlas color scheme.

## 4. Success Criteria

- [ ] `get_project_schema` MCP tool returns IFC classes, attribute keys, and relationship types present in a test project.
- [ ] `create_filter_set` MCP tool creates a named filter set and returns its ID.
- [ ] `add_filter_condition` MCP tool appends conditions (class, attribute, relation modes with operators) to an existing filter set.
- [ ] `apply_filter_set_to_context` MCP tool applies a filter set to a branch and triggers frontend view refresh.
- [ ] A natural language query like "Filter for entities whose class inherits from IfcWindow" results in correct filter application.
- [ ] The Svelte chat interface streams agent responses and shows tool-call activity.
- [ ] The model configuration panel allows switching providers and models without backend changes.
- [ ] Applied filters from the agent are reflected in the 3D viewer and search state within 2 seconds.

## 5. Architecture Overview

```
┌─────────────┐     Chat message      ┌──────────────────────┐
│  Svelte UI  │ ───────────────────►  │  FastAPI Backend      │
│  Chat Panel │ ◄─────────────────── │  POST /agent/chat     │
│  + Config   │   SSE stream / resp   │                      │
└─────────────┘                       │  ┌──────────────────┐ │
       ▲                              │  │ LlamaIndex Agent │ │
       │ State sync                   │  │  (Workflow)      │ │
       │ (BroadcastChannel            │  │                  │ │
       │  or SSE events)              │  │  Discovery ─►    │ │
       │                              │  │  Validation ─►   │ │
       ▼                              │  │  Creation ─►     │ │
┌─────────────┐                       │  │  Application     │ │
│  Search     │                       │  └────────┬─────────┘ │
│  State +    │                       │           │            │
│  3D Viewer  │                       │  ┌────────▼─────────┐ │
└─────────────┘                       │  │  MCP Tool Layer  │ │
                                      │  │  (4 tools)       │ │
                                      │  └────────┬─────────┘ │
                                      │           │            │
                                      │  ┌────────▼─────────┐ │
                                      │  │  Existing DB/    │ │
                                      │  │  Filter Engine   │ │
                                      │  └──────────────────┘ │
                                      └──────────────────────┘
```

## 6. Key Dependencies

- **LlamaIndex** (`llama-index-core`, `llama-index-llms-openai`, `llama-index-llms-anthropic`, `llama-index-llms-google`, `llama-index-llms-ollama`)
- **MCP SDK** (`mcp` Python package for tool definition, or custom tool wrappers following MCP JSON-RPC spec)
- Existing FEAT-001 filter engine (db.py, filter_operators.py, queries.py)
- Existing IFC schema loader (ifc_schema_loader.py, ifc_4_3_schema.json)
