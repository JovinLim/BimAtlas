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
