---
features:
  - feature_id: feature_001_dynamic_filter_sets
    name: Dynamic Filter Sets & Attribute Search
    description: |
      Named, configurable filter sets stored as JSONB. Users create filter sets (e.g. IfcClass = 'IfcWall' AND FireRating = '2HR'), save them to a branch, and toggle them on/off to compose complex database views. **Filter logic tree:** Nested Match ALL / Match ANY trees (max depth 2) stored in filters JSONB; canonical group/leaf schema with legacy flat-array compatibility. Strictly relational JSONB attribute filtering—no graph traversal. GraphQL mutations (create/update/delete filter sets), apply/unapply via branch_applied_filter_sets, and Search page filter set editor (FilterTreeEditor, AppliedFilterSet) with color-coded entity highlighting and cross-window sync (BroadcastChannel, localStorage, postMessage).
    status: implemented
    priority: high
  - feature_id: graph_view
    name: Graph View
    description: |
      3D force-directed graph visualization of IFC entities and their relationships. Renders nodes (spatial containers, products) and edges (topology from Apache AGE). Supports selection, node labels, and branch/revision scoping. Built with 3d-force-graph and Three.js.
    status: implemented
    priority: core
  - feature_id: feature_002_revision_search
    name: Active-Project Revision Search & Import UX
    description: |
      Search and filter revisions for the active project by author, ifc_filename, commit_message, or created_at. Import IFC flow warns that a new revision is created; no manual empty revision creation allowed. Relational queries only—no AGE Cypher.
    status: draft
    priority: high
  - feature_id: feature_003_entities_spreadsheet
    name: Entities Spreadsheet
    description: |
      Popup table view of currently filtered IFC entities with lock/unlock rows, protected columns (e.g. IfcClass), and a split layout: top entity table, bottom sheet for quantity surveying or other spreadsheet-style interactions. Data source is searchState.products.
    status: implemented
    priority: high
  - feature_id: feature_004_agentic_filtering_framework
    name: Agentic Filtering Framework (Direct API + IFC Skill Guardrails)
    description: |
      Natural language filtering interface powered by LlamaIndex agent orchestration and direct API tools. Users describe filter intent in plain language; the agent follows a domain-safe flow: **search_skills** (pgvector-backed semantic search over learned IFC mappings), **discover_api** (curated OpenAPI + GraphQL with IFC cheat-sheet), **execute_request** (HTTP to BimAtlas API), **search_web** (duckduckgo-search for up-to-date IFC docs, building codes, specs; prefers buildingSMART sites), **list_uploaded_files**/ **read_uploaded_file** (attachments), and **ask_user_for_guidance** when knowledge gaps exist. New mappings are persisted via **save_ifc_skill**. Svelte chat UI at /agent with streaming SSE, tool-call transparency, guidance_request rendering for escalation, token usage and cost display per response (via TokenCountingHandler + pricing module), saved agent configs (IfcAgent), persistent chat history, and provider-agnostic LLM configuration. State sync via /stream/agent-events.
    status: implemented
    priority: high
  - feature_id: feature_005_validation_schema_management
    name: Validation Schema Management & Subgraph Validation Engine
    description: |
      Integrated IFC validation framework where validation rules (IfcValidation) and grouping schemas (IfcValidationSchema) are first-class graph citizens stored in ifc_entity. Supports attribute checks, inheritance-aware validation, and subgraph/relationship-scoped validation via Apache AGE Cypher traversals. Schema Browser UI at /schema for browsing schemas, creating/editing rules, and linking rules to schemas. Validation run results at /validation. GraphQL CRUD and runValidation mutation. MCP tools run_validation and list_validation_schemas for agentic workflows.
    status: implemented
    priority: high
  - feature_id: feature_006_saved_views_bcf_compliant
    name: Saved Views (BCF-Compliant)
    description: |
      BCF-compliant saved views for BIM model navigation. Camera and clipping persisted in bcf_camera_state (perspective/orthogonal, clipping planes) and ui_filters JSONB; views linked to reusable filter sets via view_filter_sets. Dedicated /views popup route with list, create/edit form, and filter-set attachment. Cross-tab protocol (LOAD_VIEW, TOGGLE_GHOST_MODE) applies view state and ghost-mode overrides in the main viewer without mutating saved records.
    status: implemented
    priority: high
  - feature_id: feature_007_viewer_runtime_decoupling
    name: Viewer Runtime Decoupling & Cross-Popup Reload Progress
    description: |
      Viewer rendering logic is decoupled from the main shell into a dedicated Viewer runtime route. Geometry now streams directly in the viewer popup using active project/branch/revision context, with branch filter-set changes propagated across Viewer, Graph, and Table via BroadcastChannel reload messages. Loading overlays show progressive percentages and entity/relationship counters during reload cycles.
    status: implemented
    priority: high
---

BimAtlas Product Overview
High-Level Domain
BimAtlas is a scalable web application designed to parse, visualize, and modify Industry Foundation Classes (IFC) data for the built environment. It tackles the strict hierarchical complexity of schemas like IFC 4.3 by treating the IFC data as a manipulable, version-controlled graph. The application allows multidisciplinary teams (Architecture, MEP, Structural) to collaborate on large-scale models through a Git-like system of projects, branches, and revisions, enabling parallel workflows and conflict resolution without data degradation.

Architecture
BimAtlas utilizes a Hybrid Relational-Graph Architecture with a Temporal Database pattern (SCD Type 2).

Unified Entity Core: All physical elements, property sets, and relationship objects are flattened into a single ifc_entity table.

Temporal Versioning: Object identity (ifc_global_id) is decoupled from database state (entity_id). Changes create new immutable rows tracked via created_in_revision_id and obsoleted_in_revision_id.

JSONB Attribute Payload: Deep EXPRESS schema inheritance and property sets are flattened into a highly indexed JSONB column, utilizing "type": "entity_ref" tags to dictate relational pointers.

Graph Overlay: Relational data is synchronized with an Apache AGE graph. Topological relationships (e.g., spatial containment, piping networks) are traversed using Cypher, while heavy data payloads remain in Postgres.

Merge Request Engine: A staging framework compares branches, calculates diffs (attribute, geometry, topology), and logs collisions for user resolution before committing merges.

Design Principles & Integration
Deployable & Extensible: The platform is container-native, designed to be easily deployed on-premise or in the cloud to suit unique organizational data-sovereignty requirements. Its modular architecture allows developers to easily extend validation rulesets and GraphQL schemas for bespoke use cases.

AI & Orchestration Ready: BimAtlas natively supports AI integration through two mechanisms: (1) The Agentic Filtering Framework uses direct API tools (discover_api, execute_request, search_skills, search_web, list_uploaded_files, read_uploaded_file, ask_user_for_guidance, save_ifc_skill) orchestrated by an LLM agent. A domain-safe policy enforces search-before-create: the agent searches pgvector-backed IFC skills first, reads the discover_api cheat-sheet, uses search_web for external IFC/buildingSMART references when needed, escalates via ask_user_for_guidance on ambiguity, and saves new mappings via save_ifc_skill. Token usage and cost (USD) are tracked per response and displayed in the chat UI. (2) Standalone tools (run_validation, list_validation_schemas) enable agents to trigger validation runs and browse schemas. Agents can query the active branch state, analyze piping networks, or flag validation errors against IfcValidation rules.

Tech Stack
Backend: Python, FastAPI, GraphQL (Strawberry). REST endpoints for agent chat, configs, chats; SSE for /stream/ifc-products and /stream/agent-events.

Frontend: SvelteKit (Svelte 5), Three.js, 3d-force-graph. Routes: / (main shell), /viewer (decoupled runtime), /search, /graph, /table, /attributes, /agent, /schema, /validation, /views. Filter logic tree: FilterTreeEditor (nested Match ALL/ANY, max depth 2), AppliedFilterSet, FilterGuide, AppliedDisplayOrderPanel. Popup routes (viewer, attributes, graph, table, schema, validation, views) sync with shell context via BroadcastChannel; filter-set reload events trigger coordinated data refresh and progress overlays across Viewer/Graph/Table.

Agent Layer: LlamaIndex for agent orchestration; provider-agnostic LLM support (OpenAI, Anthropic, Google, Ollama, Custom). Agent configs and chat history persisted in PostgreSQL. IFC skills (learned mappings) stored in pgvector for semantic search. TokenCountingHandler tracks usage; pricing module computes cost (USD) per model; usage and cost displayed at bottom of each assistant message.

Database: PostgreSQL with Apache AGE (Cypher graph queries) and pgvector (semantic skill search). Single container via custom Docker image (AGE + pgvector).

Graph Engine: Apache AGE (PostgreSQL extension for Cypher graph queries).

Data Storage: JSONB with GIN indexing for schemaless attribute and property queries. BYTEA for lossless raw 3D geometry storage (e.g., Swept Solid, BREP).
