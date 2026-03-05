---
features:
  - feature_id: feature_001_dynamic_filter_sets
    name: Dynamic Filter Sets & Attribute Search
    description: |
      Named, configurable filter sets stored as JSONB. Users create filter sets (e.g. IfcClass = 'IfcWall' AND FireRating = '2HR'), save them to a branch, and toggle them on/off to compose complex database views. Strictly relational JSONB attribute filtering—no graph traversal.
    status: draft
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
    name: Agentic Filtering Framework (MCP + LlamaIndex)
    description: |
      Natural language filtering interface powered by LlamaIndex agent orchestration and MCP tools. Users describe filter intent in plain language; the agent discovers the project schema, validates IFC classes and operators, constructs filter sets, and applies them to the active view. Svelte chat UI with streaming responses, tool-call transparency, and provider-agnostic LLM configuration (OpenAI, Anthropic, Ollama).
    status: draft
    priority: high
  - feature_id: feature_005_validation_schema_management
    name: Validation Schema Management & Subgraph Validation Engine
    description: |
      Integrated IFC validation framework where validation rules (IfcValidation) and grouping schemas (IfcValidationSchema) are first-class graph citizens stored in ifc_entity. Supports attribute checks, inheritance-aware validation, and subgraph/relationship-scoped validation via Apache AGE Cypher traversals. Includes a Schema Browser UI popup and MCP tool stubs for agentic workflows.
    status: draft
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

AI & Orchestration Ready (MCP): BimAtlas natively supports AI integration by exposing its hybrid relational-graph data through the Model Context Protocol (MCP).

This provides a standardized interface for AI agents (like Claude or custom LLMs) to securely query the active state of a branch, analyze complex piping infrastructure networks for clashes, or automatically flag validation errors against the validation_rule tables.

Tech Stack
Backend: Python, GraphQL (via the strawberry package).

Integration Layer: Model Context Protocol (MCP) Server for AI agent orchestration.

Database: PostgreSQL.

Graph Engine: Apache AGE (PostgreSQL extension for Cypher graph queries).

Data Storage: \* JSONB with GIN indexing for schemaless attribute and property queries.

BYTEA for lossless raw 3D geometry storage (e.g., Swept Solid, BREP).
