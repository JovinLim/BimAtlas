---
name: read-feature-overview
description: Read product overview from overview.md for feature context. Use when planning or executing feature work under .cursor/product/features/, when the agent needs product-level domain knowledge, or when adding feature descriptions to active_task or plan files.
---

# Read Feature Overview

This skill ensures agents have product-level context when working on features. It also defines how to add feature descriptions in YAML frontmatter.

## When to Use

Use this skill when:

- Planning or executing tasks under `.cursor/product/features/`.
- The agent needs to understand BimAtlas domain, architecture, or tech stack.
- Adding or updating feature descriptions in `active_task.md`, `active_task.json`, or plan files.

## Instructions

### 1. Read the Product Overview

Before generating plans or executing feature work, read:

- **`.cursor/product/overview.md`** – Product overview including:
  - High-level domain (IFC, version-controlled graph, Git-like projects/branches/revisions)
  - Architecture (Hybrid Relational-Graph, Temporal DB, JSONB, Apache AGE)
  - Design principles (Deployable, AI/MCP ready)
  - Tech stack (Python, GraphQL, PostgreSQL, AGE)

Use this context to ensure plans and implementations align with the product's architecture and constraints.

### 2. Feature Description in YAML Frontmatter

When updating `active_task.md` (or creating plan artifacts), include a feature description in YAML frontmatter so downstream agents have concise context.

**Format for `active_task.md`:**

```yaml
---
status: ready_for_execution
feature_id: feature_002_revision_search
feature_description: |
  Revision search and Import IFC UX for the active project. Users search revisions
  by author, ifc_filename, commit_message, or created_at. Import IFC must warn that
  a new revision is created; no manual empty revision creation allowed.
---
```

**Fields:**

| Field | Purpose |
|-------|---------|
| `status` | Task state (e.g. `pending`, `ready_for_execution`, `complete`) |
| `feature_id` | Feature directory name (e.g. `feature_001_dynamic_filter_sets`) |
| `feature_description` | One- to three-sentence summary of the feature, derived from `prd.md` and `overview.md` |

**Deriving the description:**

- Read the feature's `prd.md` (Problem Statement, Core Requirements).
- Cross-reference with `overview.md` for domain terms (e.g. revision, branch, IFC).
- Write a concise summary that captures scope and constraints.

### 3. For JSON `active_task.json`

When using `active_task.json`, add a `feature_description` field under `metadata`:

```json
{
  "metadata": {
    "feature_id": "feature_002_revision_search",
    "feature_description": "Revision search and Import IFC UX for the active project. Users search revisions by author, ifc_filename, commit_message, or created_at. Import IFC must warn that a new revision is created; no manual empty revision creation allowed.",
    "plan_reference": "...",
    "assigned_agent": "...",
    "last_updated": "..."
  },
  ...
}
```
