---
name: feat004-agentic-filtering-framework
overview: |
  Implement an Agentic Filtering Framework for BimAtlas that allows users to perform complex IFC data audits and visualization queries via natural language. The system exposes four MCP tools (get_project_schema, create_filter_set, add_filter_condition, apply_filter_set_to_context) to a LlamaIndex agent, with a Svelte chat interface for interaction and SSE-based state synchronization.
todos:
  - id: step-01-mcp-tool-schemas
    content: "Define JSON-RPC schemas for the four MCP tools and create the MCP tool registry module."
    status: pending
  - id: step-02-get-project-schema-tool
    content: "Implement get_project_schema MCP tool that returns IFC classes, attribute keys, and relationship types for a branch/revision."
    status: pending
  - id: step-03-create-filter-set-tool
    content: "Implement create_filter_set MCP tool wrapping existing db.create_filter_set."
    status: pending
  - id: step-04-add-filter-condition-tool
    content: "Implement add_filter_condition MCP tool that appends a filter condition to an existing filter set."
    status: pending
  - id: step-05-apply-filter-set-tool
    content: "Implement apply_filter_set_to_context MCP tool wrapping db.apply_filter_sets with event emission."
    status: pending
  - id: step-06-llamaindex-agent-workflow
    content: "Implement LlamaIndex Workflow with Discovery, Validation, Creation, Application steps and tool bindings."
    status: pending
  - id: step-07-agent-api-endpoint
    content: "Create POST /agent/chat FastAPI endpoint with SSE streaming response for agent interaction."
    status: pending
  - id: step-08-agent-events-sse
    content: "Create GET /stream/agent-events SSE endpoint for pushing filter-applied notifications to the frontend."
    status: pending
  - id: step-09-frontend-chat-component
    content: "Build Svelte chat panel component with message list, input, and tool-call activity display."
    status: pending
  - id: step-10-frontend-model-config
    content: "Build Svelte model configuration panel (Provider, Model, API Key) with localStorage persistence."
    status: pending
  - id: step-11-frontend-state-sync
    content: "Wire agent-events SSE to Svelte search state to trigger view refresh on filter application."
    status: pending
  - id: step-12-frontend-chat-route
    content: "Create /agent route or integrate chat panel into main page sidebar following existing popup conventions."
    status: pending
  - id: step-13-backend-tests
    content: "Add pytest tests for MCP tools, agent workflow, and agent API endpoint."
    status: pending
  - id: step-14-integration-test
    content: "End-to-end test: natural language query → agent → filter creation → application → frontend refresh."
    status: pending
  - id: step-15-verification
    content: "Run full API test suite, frontend type checks, and validate end-to-end scenario."
    status: pending
isProject: true
---

# FEAT-004 Agentic Filtering Framework — Implementation Plan

## Goal

Implement an AI-powered natural language filtering interface for BimAtlas that uses MCP tools orchestrated by a LlamaIndex agent to translate user queries into filter set operations, with a Svelte chat UI and real-time state synchronization.

## Architecture Diagram

```
┌───────────────────────────────────────────────────────────────────┐
│                         SVELTE FRONTEND                           │
│                                                                   │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────────────┐ │
│  │ Chat Panel   │  │ Model Config │  │ Main View (3D + Graph)   │ │
│  │ - Messages   │  │ - Provider   │  │ - Viewport               │ │
│  │ - Input      │  │ - Model      │  │ - Search State           │ │
│  │ - Tool calls │  │ - API Key    │  │ - Applied Filter Sets    │ │
│  └──────┬───────┘  └──────┬───────┘  └────────────┬─────────────┘ │
│         │                 │                        │               │
│         │    POST /agent/chat                      │               │
│         │    { message, provider,           SSE /stream/           │
│         │      model, apiKey,             agent-events             │
│         │      branchId, revision }         │                      │
└─────────┼─────────────────┼─────────────────┼──────────────────────┘
          │                 │                 │
          ▼                 ▼                 ▲
┌───────────────────────────────────────────────────────────────────┐
│                       FASTAPI BACKEND                             │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │  POST /agent/chat  (SSE streaming response)                │   │
│  │  - Receives: message, LLM config, branch context           │   │
│  │  - Instantiates LlamaIndex agent with MCP tools            │   │
│  │  - Streams: thought steps, tool calls, final answer         │   │
│  └──────────────────────────┬─────────────────────────────────┘   │
│                             │                                     │
│  ┌──────────────────────────▼─────────────────────────────────┐   │
│  │              LLAMAINDEX WORKFLOW                            │   │
│  │                                                             │   │
│  │  ┌───────────┐  ┌────────────┐  ┌──────────┐  ┌─────────┐ │   │
│  │  │ Discovery │─►│ Validation │─►│ Creation │─►│ Apply   │ │   │
│  │  │           │  │            │  │          │  │         │ │   │
│  │  │ Call      │  │ Verify     │  │ Call     │  │ Call    │ │   │
│  │  │ get_      │  │ classes,   │  │ create_  │  │ apply_  │ │   │
│  │  │ project_  │  │ attrs,     │  │ filter_  │  │ filter_ │ │   │
│  │  │ schema    │  │ operators  │  │ set +    │  │ set_to_ │ │   │
│  │  │           │  │ exist in   │  │ add_     │  │ context │ │   │
│  │  │           │  │ schema     │  │ filter_  │  │         │ │   │
│  │  │           │  │            │  │ condition│  │ + emit  │ │   │
│  │  └───────────┘  └────────────┘  └──────────┘  │ event   │ │   │
│  │                                                └─────────┘ │   │
│  └────────────────────────────────────────────────────────────┘   │
│                             │                                     │
│  ┌──────────────────────────▼─────────────────────────────────┐   │
│  │                MCP TOOL LAYER                              │   │
│  │  src/services/agent/mcp_tools.py                           │   │
│  │                                                             │   │
│  │  ┌─────────────────┐  ┌─────────────────┐                 │   │
│  │  │ get_project_    │  │ create_filter_  │                 │   │
│  │  │ schema          │  │ set             │                 │   │
│  │  └────────┬────────┘  └────────┬────────┘                 │   │
│  │           │                    │                            │   │
│  │  ┌────────┴────────┐  ┌───────┴─────────┐                 │   │
│  │  │ add_filter_     │  │ apply_filter_   │                 │   │
│  │  │ condition       │  │ set_to_context  │                 │   │
│  │  └────────┬────────┘  └────────┬────────┘                 │   │
│  │           │                    │                            │   │
│  └───────────┼────────────────────┼───────────────────────────┘   │
│              │                    │                                │
│  ┌───────────▼────────────────────▼───────────────────────────┐   │
│  │          EXISTING BACKEND LAYER                            │   │
│  │  db.py: filter CRUD, entity queries, filter engine         │   │
│  │  ifc_schema_loader.py: get_descendants, hierarchy          │   │
│  │  filter_operators.py: operator vocabulary                  │   │
│  │  queries.py: GraphQL resolvers (reused internally)         │   │
│  └────────────────────────────────────────────────────────────┘   │
│                             │                                     │
│  ┌──────────────────────────▼─────────────────────────────────┐   │
│  │            POSTGRESQL + APACHE AGE                         │   │
│  │  ifc_entity, filter_sets, branch_applied_filter_sets,      │   │
│  │  validation_rule (IFC schema), ifc_schema                  │   │
│  └────────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────┘
```

## MCP Tool JSON-RPC Schemas

### Tool 1: `get_project_schema`

```json
{
  "name": "get_project_schema",
  "description": "Returns the IFC schema context for a project branch: unique IFC classes present, their attributes, available filter operators, and relationship types. Use this first to understand what data exists before creating filters.",
  "parameters": {
    "type": "object",
    "properties": {
      "branch_id": {
        "type": "string",
        "description": "UUID of the branch to inspect"
      },
      "revision": {
        "type": "integer",
        "description": "Revision sequence number (null = latest)",
        "nullable": true
      }
    },
    "required": ["branch_id"]
  },
  "returns": {
    "type": "object",
    "properties": {
      "ifc_classes": {
        "type": "array",
        "items": { "type": "string" },
        "description": "Unique IFC class names present in this branch/revision (e.g. IfcWall, IfcDoor, IfcWindow)"
      },
      "ifc_class_hierarchy": {
        "type": "object",
        "description": "Map of IFC class → list of parent classes for inheritance queries",
        "additionalProperties": {
          "type": "array",
          "items": { "type": "string" }
        }
      },
      "common_attributes": {
        "type": "array",
        "items": { "type": "string" },
        "description": "Frequently occurring top-level attribute keys across entities (e.g. Name, Description, ObjectType, Tag, PropertySets)"
      },
      "relationship_types": {
        "type": "array",
        "items": { "type": "string" },
        "description": "Available IFC relationship types (e.g. IfcRelContainedInSpatialStructure, IfcRelVoidsElement)"
      },
      "filter_operators": {
        "type": "object",
        "properties": {
          "string": { "type": "array", "items": { "type": "string" } },
          "numeric": { "type": "array", "items": { "type": "string" } },
          "class": { "type": "array", "items": { "type": "string" } }
        },
        "description": "Available operators grouped by mode"
      },
      "entity_count": {
        "type": "integer",
        "description": "Total number of entities in this branch/revision"
      }
    }
  }
}
```

### Tool 2: `create_filter_set`

```json
{
  "name": "create_filter_set",
  "description": "Creates a new empty named filter set on a branch. Returns the filter set ID for subsequent add_filter_condition calls. The filter set starts with AND logic by default.",
  "parameters": {
    "type": "object",
    "properties": {
      "branch_id": {
        "type": "string",
        "description": "UUID of the branch to create the filter set on"
      },
      "name": {
        "type": "string",
        "description": "Human-readable name for the filter set (e.g. 'Fire-rated walls', 'Window hierarchy filter')"
      },
      "logic": {
        "type": "string",
        "enum": ["AND", "OR"],
        "description": "Intra-set logic for combining filter conditions. Default: AND",
        "default": "AND"
      }
    },
    "required": ["branch_id", "name"]
  },
  "returns": {
    "type": "object",
    "properties": {
      "filter_set_id": { "type": "string", "description": "UUID of the created filter set" },
      "name": { "type": "string" },
      "logic": { "type": "string" },
      "filters": { "type": "array", "items": {}, "description": "Empty array (no conditions yet)" }
    }
  }
}
```

### Tool 3: `add_filter_condition`

```json
{
  "name": "add_filter_condition",
  "description": "Appends a filter condition to an existing filter set. Each condition targets a mode (class, attribute, or relation) with a specific operator and value. Multiple conditions can be added by calling this tool repeatedly.",
  "parameters": {
    "type": "object",
    "properties": {
      "filter_set_id": {
        "type": "string",
        "description": "UUID of the filter set to add the condition to"
      },
      "mode": {
        "type": "string",
        "enum": ["class", "attribute", "relation"],
        "description": "Filter mode: 'class' for IFC class filtering, 'attribute' for JSONB attribute filtering, 'relation' for graph relationship filtering"
      },
      "operator": {
        "type": "string",
        "description": "Operator to apply. Class mode: is, is_not, inherits_from. Attribute string: is, is_not, contains, not_contains, starts_with, ends_with, is_empty, is_not_empty. Attribute numeric: equals, not_equals, gt, lt, gte, lte."
      },
      "ifc_class": {
        "type": "string",
        "description": "IFC class name (required for mode='class', e.g. 'IfcWall', 'IfcWindow')",
        "nullable": true
      },
      "attribute": {
        "type": "string",
        "description": "Attribute key to filter on (required for mode='attribute', e.g. 'Name', 'FireRating', 'PropertySets')",
        "nullable": true
      },
      "value": {
        "type": "string",
        "description": "Value to compare against (not required for is_empty/is_not_empty operators)",
        "nullable": true
      },
      "value_type": {
        "type": "string",
        "enum": ["string", "numeric"],
        "description": "Value type for attribute mode. Use 'numeric' for gt/lt/gte/lte operators. Default: string",
        "nullable": true
      },
      "relation": {
        "type": "string",
        "description": "Relationship type (required for mode='relation', e.g. 'IfcRelVoidsElement')",
        "nullable": true
      }
    },
    "required": ["filter_set_id", "mode", "operator"]
  },
  "returns": {
    "type": "object",
    "properties": {
      "filter_set_id": { "type": "string" },
      "name": { "type": "string" },
      "logic": { "type": "string" },
      "filters": {
        "type": "array",
        "description": "Updated list of all filter conditions in the set"
      },
      "condition_count": { "type": "integer", "description": "Total number of conditions after addition" }
    }
  }
}
```

### Tool 4: `apply_filter_set_to_context`

```json
{
  "name": "apply_filter_set_to_context",
  "description": "Applies one or more filter sets to a branch, updating the active view. This replaces any previously applied filter sets on the branch. After application, the frontend view will refresh to show only matching entities.",
  "parameters": {
    "type": "object",
    "properties": {
      "branch_id": {
        "type": "string",
        "description": "UUID of the branch to apply filters to"
      },
      "filter_set_ids": {
        "type": "array",
        "items": { "type": "string" },
        "description": "List of filter set UUIDs to apply"
      },
      "combination_logic": {
        "type": "string",
        "enum": ["AND", "OR"],
        "description": "Logic for combining multiple filter sets. Default: AND",
        "default": "AND"
      }
    },
    "required": ["branch_id", "filter_set_ids"]
  },
  "returns": {
    "type": "object",
    "properties": {
      "applied_filter_sets": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "id": { "type": "string" },
            "name": { "type": "string" },
            "condition_count": { "type": "integer" }
          }
        }
      },
      "combination_logic": { "type": "string" },
      "matched_entity_count": {
        "type": "integer",
        "description": "Number of entities matching the applied filters"
      }
    }
  }
}
```

## LlamaIndex Workflow Design

### Event-Driven Workflow Steps

The agent handles a request like "Filter for only entities which IFC class inherits from IfcWindow" through four sequential steps:

#### Step 1: Discovery

**Trigger:** User message received.
**Action:** Call `get_project_schema(branch_id, revision)` to retrieve the current IFC context.
**Output Event:** `SchemaDiscoveredEvent` containing classes, attributes, operators, relationships.
**Reasoning:** The LLM now knows what IFC classes exist (e.g., `IfcWindow`, `IfcWindowStandardCase`), what attributes are available, and which operators can be used. This prevents hallucination.

#### Step 2: Validation

**Trigger:** `SchemaDiscoveredEvent` received.
**Action:** The LLM analyzes the user's intent against the discovered schema:
  - Parse intent: "inherits from IfcWindow" → mode=`class`, operator=`inherits_from`, ifc_class=`IfcWindow`.
  - Validate `IfcWindow` exists in `ifc_classes` or `ifc_class_hierarchy`.
  - Validate `inherits_from` is available in `filter_operators.class`.
  - If validation fails, ask the user for clarification or suggest alternatives.
**Output Event:** `ValidationPassedEvent` with parsed filter plan (list of conditions to create).

#### Step 3: Creation

**Trigger:** `ValidationPassedEvent` received.
**Action:** Execute tool calls to build the filter set:
  1. Call `create_filter_set(branch_id, name="IfcWindow inheritance filter", logic="AND")` → get `filter_set_id`.
  2. Call `add_filter_condition(filter_set_id, mode="class", operator="inherits_from", ifc_class="IfcWindow")`.
  3. (If multi-condition: repeat `add_filter_condition` for each parsed condition.)
**Output Event:** `FilterSetCreatedEvent` with `filter_set_id` and condition summary.

#### Step 4: Application

**Trigger:** `FilterSetCreatedEvent` received.
**Action:** Call `apply_filter_set_to_context(branch_id, filter_set_ids=[filter_set_id], combination_logic="AND")`.
**Output Event:** `FilterAppliedEvent` with matched entity count.
**Side Effect:** Backend emits an SSE event on `/stream/agent-events` notifying the frontend to refresh.
**Final Response:** "I've applied a filter for entities inheriting from IfcWindow. Found {N} matching entities including IfcWindow, IfcWindowStandardCase, etc."

### Complex Multi-Condition Example

User: "Show me fire-rated walls with a rating above 2 hours"

1. **Discovery:** Call `get_project_schema` → confirms `IfcWall` exists, `FireRating` attribute found in common attributes.
2. **Validation:** Parse two conditions:
   - Condition 1: mode=`class`, operator=`is`, ifc_class=`IfcWall`
   - Condition 2: mode=`attribute`, operator=`gt`, attribute=`FireRating`, value=`2`, value_type=`numeric`
3. **Creation:**
   - `create_filter_set(branch_id, "Fire-rated walls >2hr", "AND")`
   - `add_filter_condition(filter_set_id, mode="class", operator="is", ifc_class="IfcWall")`
   - `add_filter_condition(filter_set_id, mode="attribute", operator="gt", attribute="FireRating", value="2", value_type="numeric")`
4. **Application:** `apply_filter_set_to_context(branch_id, [filter_set_id], "AND")`

## State Management Strategy

### Backend → Frontend Sync

```
Agent applies filter ──► DB updated ──► SSE event emitted
                                              │
                                              ▼
                                    Frontend EventSource
                                              │
                                              ▼
                                    searchState.appliedFilterSets = refreshed
                                              │
                                              ▼
                                    Re-fetch /stream/ifc-products
                                              │
                                              ▼
                                    3D Viewer + Graph updated
```

**Mechanism:** Dedicated SSE endpoint `GET /stream/agent-events?branch_id={id}`.

Events emitted:
- `filter-applied`: `{ type: "filter-applied", branchId, filterSetIds, matchedCount, timestamp }`
- `agent-thinking`: `{ type: "agent-thinking", step: "discovery|validation|creation|application" }`
- `agent-error`: `{ type: "agent-error", message: string }`

### Frontend State Flow

1. **Chat sends message** → `POST /agent/chat` with SSE response.
2. **SSE stream delivers** agent thoughts, tool calls, and final answer to the chat panel.
3. **On `filter-applied` event** (from `/stream/agent-events`):
   - Update `searchState.appliedFilterSets` by re-fetching `appliedFilterSets(branchId)` GraphQL query.
   - Trigger product stream refresh (existing `handleApplyFilterSets` flow in `+page.svelte`).
4. **BroadcastChannel** propagation ensures search popup, table popup, and other windows stay in sync.

### Svelte State Integration

```typescript
// In agent/protocol.ts (new file)
export const AGENT_CHANNEL = 'bimatlas-agent';

export interface AgentMessage {
  role: 'user' | 'assistant' | 'tool';
  content: string;
  toolCalls?: ToolCallInfo[];
  timestamp: string;
}

export interface ToolCallInfo {
  name: string;
  arguments: Record<string, unknown>;
  result?: unknown;
  status: 'pending' | 'complete' | 'error';
}

export interface AgentConfig {
  provider: 'openai' | 'anthropic' | 'ollama' | 'custom';
  model: string;
  apiKey: string;
  baseUrl?: string;  // For Ollama / custom endpoints
}

export type AgentEvent =
  | { type: 'filter-applied'; branchId: string; filterSetIds: string[]; matchedCount: number }
  | { type: 'agent-thinking'; step: string }
  | { type: 'agent-error'; message: string };
```

## Implementation Steps

### Step 1: Define MCP Tool Schemas and Registry (`step-01-mcp-tool-schemas`)

**Files to create:**
- `apps/api/src/services/agent/__init__.py`
- `apps/api/src/services/agent/mcp_tools.py`

**Actions:**
- [ ] Create the `services/agent/` package.
- [ ] Define the four tool functions as Python callables with full docstrings following MCP tool specification.
- [ ] Create a `get_tool_definitions()` function that returns LlamaIndex `FunctionTool` wrappers for each tool.
- [ ] Each tool must accept a `context` dict (branch_id, revision) injected at agent creation time.

**Constraint from lessons_learned:** All IDs are UUID strings. Query attributes via JSONB operators. Do not touch geometry.

### Step 2: Implement `get_project_schema` Tool (`step-02-get-project-schema-tool`)

**Files to modify:**
- `apps/api/src/services/agent/mcp_tools.py`
- `apps/api/src/db.py` (add helper if needed)

**Actions:**
- [ ] Implement `get_project_schema(branch_id, revision)` that:
  1. Calls `fetch_distinct_ifc_classes_at_revision(rev, branch_id)` for unique IFC classes.
  2. Samples attributes from `ifc_entity.attributes` JSONB to extract common top-level keys.
  3. Returns operator vocabulary from `filter_operators.py`.
  4. Returns relationship types from `IfcRelationshipType` enum.
  5. Builds a class hierarchy map from `ifc_schema_loader` for present classes.
- [ ] Add `fetch_common_attribute_keys(rev, branch_id, limit=50)` helper to `db.py` if needed (query distinct top-level JSONB keys across entities).
- [ ] Add `fetch_entity_count_at_revision(rev, branch_id)` helper to `db.py` if needed.

### Step 3: Implement `create_filter_set` Tool (`step-03-create-filter-set-tool`)

**Files to modify:**
- `apps/api/src/services/agent/mcp_tools.py`

**Actions:**
- [ ] Implement `create_filter_set(branch_id, name, logic="AND")` that:
  1. Calls `db.create_filter_set(branch_id, name, logic, filters_json=[])` to create an empty set.
  2. Returns `{ filter_set_id, name, logic, filters: [] }`.
- [ ] Validate branch_id is a valid UUID before calling DB.

### Step 4: Implement `add_filter_condition` Tool (`step-04-add-filter-condition-tool`)

**Files to modify:**
- `apps/api/src/services/agent/mcp_tools.py`
- `apps/api/src/db.py` (if `fetch_filter_set` doesn't return filters, add accessor)

**Actions:**
- [ ] Implement `add_filter_condition(filter_set_id, mode, operator, ...)` that:
  1. Fetches existing filter set via `db.fetch_filter_set(filter_set_id)`.
  2. Validates the operator is valid for the mode using `filter_operators.is_valid_operator`.
  3. Constructs the new filter condition dict.
  4. Appends to existing filters array.
  5. Calls `db.update_filter_set(filter_set_id, filters_json=updated_filters)`.
  6. Returns updated filter set with condition count.
- [ ] Handle edge cases: invalid filter_set_id, invalid operator/mode combination, missing required fields per mode.

### Step 5: Implement `apply_filter_set_to_context` Tool (`step-05-apply-filter-set-tool`)

**Files to modify:**
- `apps/api/src/services/agent/mcp_tools.py`
- `apps/api/src/services/agent/events.py` (new — event bus for SSE notifications)

**Actions:**
- [ ] Implement `apply_filter_set_to_context(branch_id, filter_set_ids, combination_logic="AND")` that:
  1. Calls `db.apply_filter_sets(branch_id, filter_set_ids, combination_logic)`.
  2. Optionally counts matched entities via `db.fetch_entities_with_filter_sets(...)`.
  3. Emits a `filter-applied` event to the SSE event bus.
  4. Returns applied set summary with matched entity count.
- [ ] Create `events.py` with a simple in-process event bus (asyncio.Queue or similar) for SSE fan-out.

### Step 6: LlamaIndex Agent Workflow (`step-06-llamaindex-agent-workflow`)

**Files to create:**
- `apps/api/src/services/agent/workflow.py`
- `apps/api/src/services/agent/llm_factory.py`

**Actions:**
- [ ] Create `llm_factory.py` with `create_llm(provider, model, api_key, base_url=None)` that returns the appropriate LlamaIndex LLM instance (OpenAI, Anthropic, Ollama, etc.).
- [ ] Create `workflow.py` with the `AgentWorkflow` class (or use LlamaIndex `Workflow` if evaluating it provides benefits over `ReActAgent`):
  1. Accept user message, branch context, and LLM config.
  2. Bind the four MCP tools with branch context injected.
  3. Use system prompt that instructs the agent to follow Discovery → Validation → Creation → Application.
  4. Stream intermediate steps (tool calls, reasoning) as SSE events.
- [ ] System prompt must include:
  - Available tools and their semantics.
  - Instruction to always call `get_project_schema` first.
  - Instruction to validate class/attribute names against schema before using them.
  - Operator vocabulary reference.
  - IFC inheritance explanation (inherits_from resolves to class + all descendants).

**LlamaIndex Workflow vs ReActAgent decision:**
- Evaluate LlamaIndex `Workflow` (event-driven, explicit step control) vs `ReActAgent` (autonomous tool selection).
- Recommend starting with `ReActAgent` for simplicity, with a strong system prompt guiding the Discovery → Validation → Creation → Application pattern.
- If the agent frequently skips discovery or creates invalid filters, upgrade to explicit `Workflow` with enforced step ordering.

### Step 7: Agent API Endpoint (`step-07-agent-api-endpoint`)

**Files to modify:**
- `apps/api/src/main.py`

**Actions:**
- [ ] Add `POST /agent/chat` endpoint:
  ```python
  @app.post("/agent/chat")
  async def agent_chat(body: dict = Body(...)):
      # body: { message, provider, model, apiKey, branchId, revision?, baseUrl? }
      # Returns SSE stream of agent events
  ```
- [ ] SSE events:
  - `{ type: "thinking", content: "Discovering project schema..." }`
  - `{ type: "tool_call", name: "get_project_schema", arguments: {...}, result: {...} }`
  - `{ type: "message", content: "I found 15 entities matching..." }`
  - `{ type: "error", content: "Failed to..." }`
  - `{ type: "done" }`
- [ ] API key is received per-request from the frontend and passed to the LLM factory. Never persisted.

### Step 8: Agent Events SSE Endpoint (`step-08-agent-events-sse`)

**Files to modify:**
- `apps/api/src/main.py`
- `apps/api/src/services/agent/events.py`

**Actions:**
- [ ] Add `GET /stream/agent-events?branch_id={id}` SSE endpoint.
- [ ] Uses the event bus from `events.py` to push filter-applied notifications.
- [ ] Events: `filter-applied`, `agent-thinking`, `agent-error`.
- [ ] Client connects on page load, reconnects on disconnect (standard EventSource behavior).

### Step 9: Frontend Chat Component (`step-09-frontend-chat-component`)

**Files to create:**
- `apps/web/src/lib/agent/ChatPanel.svelte`
- `apps/web/src/lib/agent/ChatMessage.svelte`
- `apps/web/src/lib/agent/ToolCallBadge.svelte`
- `apps/web/src/lib/agent/protocol.ts`

**Actions:**
- [ ] Create `protocol.ts` with `AgentMessage`, `ToolCallInfo`, `AgentConfig`, `AgentEvent` types.
- [ ] Create `ChatPanel.svelte`:
  - Message list (scrollable, auto-scroll to bottom).
  - Input textarea with send button (Enter to send, Shift+Enter for newline).
  - Loading state while agent is processing.
  - Uses Svelte 5 runes (`$state`, `$derived`) per project conventions.
- [ ] Create `ChatMessage.svelte`:
  - Renders user messages (right-aligned, blue) and assistant messages (left-aligned, gray).
  - Renders tool call badges inline showing which tools were called.
- [ ] Create `ToolCallBadge.svelte`:
  - Compact display of tool name, expandable to show arguments and results.
  - Color-coded: green (success), yellow (pending), red (error).

### Step 10: Frontend Model Configuration Panel (`step-10-frontend-model-config`)

**Files to create:**
- `apps/web/src/lib/agent/ModelConfig.svelte`

**Actions:**
- [ ] Create `ModelConfig.svelte`:
  - Provider dropdown: OpenAI, Anthropic, Ollama, Custom.
  - Model text input (with suggestions per provider, e.g., `gpt-4o`, `claude-sonnet-4-20250514`, `llama3`).
  - API Key password input.
  - Base URL input (shown only for Ollama/Custom providers).
  - Persist to localStorage via existing `persistence.ts` patterns.
  - Collapsible panel (expanded by default on first use, collapsed after configuration).

### Step 11: Frontend State Sync (`step-11-frontend-state-sync`)

**Files to modify:**
- `apps/web/src/lib/agent/protocol.ts`
- `apps/web/src/routes/+page.svelte` (or layout)

**Actions:**
- [ ] Connect to `GET /stream/agent-events?branch_id={id}` via `EventSource`.
- [ ] On `filter-applied` event:
  1. Re-fetch `appliedFilterSets(branchId)` via GraphQL.
  2. Update `searchState.appliedFilterSets`.
  3. Trigger product stream re-fetch (reuse existing `handleApplyFilterSets` logic).
- [ ] Broadcast changes via `SEARCH_CHANNEL` BroadcastChannel so search/table/graph popups stay in sync.

### Step 12: Frontend Chat Route (`step-12-frontend-chat-route`)

**Files to create/modify:**
- `apps/web/src/routes/agent/+page.svelte` (new route for popup) OR
- Modify `apps/web/src/routes/+page.svelte` to include chat as sidebar panel.

**Actions:**
- [ ] Decide: popup tab (like Graph/Search/Table) or integrated sidebar panel.
  - Recommendation: **Sidebar panel** on the main page (toggled via an "AI" or "Agent" button in the sidebar), because the agent needs branch context and should see filter changes in real-time.
  - Alternative: Popup tab following existing `BroadcastChannel` conventions.
- [ ] Wire the chat panel to the main page with branch context (branchId, revision).
- [ ] Add "Agent" button to the sidebar alongside Graph/Search/Table/Attributes buttons.

### Step 13: Backend Tests (`step-13-backend-tests`)

**Files to create:**
- `apps/api/tests/test_mcp_tools.py`
- `apps/api/tests/test_agent_workflow.py`

**Actions:**
- [ ] Test `get_project_schema`: Returns correct classes, attributes, operators for a seeded test DB.
- [ ] Test `create_filter_set`: Creates empty filter set, returns valid ID.
- [ ] Test `add_filter_condition`: Appends conditions, validates operator/mode combos, rejects invalid input.
- [ ] Test `apply_filter_set_to_context`: Applies filter set, returns matched count.
- [ ] Test agent workflow end-to-end with a mock LLM (or use `llama-index` test utilities).
- [ ] Constraint: Tests requiring `inherits_from` must use `ifc_schema_seeded` fixture.

### Step 14: Integration Test (`step-14-integration-test`)

**Actions:**
- [ ] Create a test scenario:
  1. Seed test DB with IFC entities including IfcWindow, IfcWindowStandardCase, IfcWall.
  2. Send "Filter for entities inheriting from IfcWindow" to agent endpoint (with mock LLM or scripted tool calls).
  3. Verify filter set created with `inherits_from` operator.
  4. Verify filter applied to branch.
  5. Verify entity query returns only IfcWindow + IfcWindowStandardCase entities.
- [ ] Test the SSE event bus: Verify `filter-applied` event is emitted after application.

### Step 15: Verification (`step-15-verification`)

**Actions:**
- [ ] Run full API test suite: `cd apps/api && source .venv/bin/activate && ./run_tests.sh`.
- [ ] Run frontend type checks: `cd apps/web && pnpm run check`.
- [ ] Run linting: `cd apps/api && ruff check .`.
- [ ] Validate end-to-end scenario in browser: type natural language query → see filters applied → 3D view updates.

## Constraints to Inject During Execution

- All IDs (`project_id`, `branch_id`, `revision_id`, `filter_set_id`) are UUID strings.
- Query IFC attributes through `ifc_entity.attributes` JSONB operators; do not revert to legacy scalar columns.
- Keep geometry handling opaque (`geometry BYTEA` untouched by agent tools).
- The `inherits_from` operator depends on `get_descendants()` which requires `validation_rule` to be seeded. Tests must use the `ifc_schema_seeded` fixture.
- Nested JSONB key filtering uses recursive walk; attribute keys entered by user can target keys at any depth.
- AGE graph properties use `ifc_global_id` (not `global_id`), `branch_id` as UUID string, `valid_from_rev`/`valid_to_rev` as `revision_seq` integers.
- LLM API keys must never be stored server-side. They are passed per-request from the frontend.
- MCP tools must wrap existing DB functions, not duplicate their logic.

## Dependencies to Install

### Backend (apps/api)
```bash
uv pip install llama-index-core llama-index-llms-openai llama-index-llms-anthropic llama-index-llms-ollama
```

### Frontend (apps/web)
No new npm dependencies expected. Uses existing Svelte 5, urql, and EventSource APIs.
