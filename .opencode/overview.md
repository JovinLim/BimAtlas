---
features:
  - feature_id: feature_001_dynamic_filter_sets
    name: Dynamic Filter Sets & Attribute Search
    description: |
      Named, configurable filter sets stored as JSONB. Users create filter sets (e.g. IfcClass = 'IfcWall' AND FireRating = '2HR'), save them to a branch, and toggle them on/off to compose complex database views.
    status: implemented
    priority: high
  - feature_id: graph_view
    name: Graph View
    description: |
      3D force-directed graph visualization of IFC entities and their relationships using 3d-force-graph and Three.js.
    status: implemented
    priority: core
  - feature_id: feature_002_revision_search
    name: Active-Project Revision Search & Import UX
    description: |
      Search and filter revisions for the active project by author, ifc_filename, commit_message, or created_at.
    status: draft
    priority: high
  - feature_id: feature_003_entities_spreadsheet
    name: Entities Spreadsheet
    description: |
      Popup table view of currently filtered IFC entities with lock/unlock rows and protected columns.
    status: implemented
    priority: high
  - feature_id: feature_004_agentic_filtering_framework
    name: Agentic Filtering Framework (Direct API + IFC Skill Guardrails)
    description: |
      Natural language filtering interface powered by LlamaIndex agent orchestration and direct API tools.
    status: implemented
    priority: high
  - feature_id: feature_005_validation_schema_management
    name: Validation Schema Management & Subgraph Validation Engine
    description: |
      Integrated IFC validation framework where validation rules and grouping schemas are first-class graph citizens.
    status: implemented
    priority: high
  - feature_id: feature_006_saved_views_bcf_compliant
    name: Saved Views (BCF-Compliant)
    description: |
      BCF-compliant saved views for BIM model navigation with camera and clipping persistence.
    status: implemented
    priority: high
  - feature_id: feature_007_viewer_runtime_decoupling
    name: Viewer Runtime Decoupling & Cross-Popup Reload Progress
    description: |
      Viewer rendering logic decoupled into a dedicated runtime with geometry streaming and BroadcastChannel sync.
    status: implemented
    priority: high
---

# Product Overview

## High-Level Domain

BimAtlas is a scalable web application designed to parse, visualize, and modify Industry Foundation Classes (IFC) data for the built environment. It treats IFC data as a manipulable, version-controlled graph. The application allows multidisciplinary teams (Architecture, MEP, Structural) to collaborate on large-scale models through a Git-like system of projects, branches, and revisions.

## Architecture

- **Runtime**: Container-native, deployable on-premise or cloud
- **Backend**: Python, FastAPI, GraphQL (Strawberry), PostgreSQL + Apache AGE
- **Frontend**: SvelteKit (Svelte 5), Three.js, 3d-force-graph
- **Agent Layer**: LlamaIndex for orchestration; provider-agnostic LLM support
- **Graph Engine**: Apache AGE (Cypher graph queries) with pgvector for semantic search

### Key Integration Points

- GraphQL API for data operations
- SSE endpoints for streaming (`/stream/ifc-products`, `/stream/agent-events`)
- MCP tools for agentic workflows

## Design Principles

- **Reliability**: SCD Type 2 versioning for temporal queries
- **Extensibility**: Modular architecture for validation rulesets and GraphQL schemas
- **AI Ready**: Native support via Agentic Filtering Framework and MCP tools

## Tech Stack

- Backend: Python 3.11+, FastAPI, Strawberry GraphQL, IfcOpenShell
- Frontend: SvelteKit 5, TypeScript, Three.js, 3d-force-graph
- Database: PostgreSQL with Apache AGE and pgvector extensions
- Agent: LlamaIndex Core, OpenAI/Anthropic/Google/Ollama providers
