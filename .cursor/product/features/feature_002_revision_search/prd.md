---
feature_id: "FEAT-002"
status: "draft"
priority: "high"
---

# Feature: Active-Project Revision Search & Import UX

## 1. Problem Statement

Users need to search and filter revisions for the active project (by author, ifc_filename, commit_message, or created_at). They must also be clearly informed that Import IFC creates a new revision, and must not be able to create an empty revision manually.

## 2. Core Requirements

- **Req 1 (Revision search):** The system must support searching/filtering revisions for the active project's branch by author_id, ifc_filename, commit_message, and created_at. Branch scoping is mandatory; all filters must be parameterized (no raw SQL from user input).
- **Req 2 (Import IFC messaging):** The Import IFC flow must explicitly notify the user that a new revision will be created (e.g. warning text in the modal; optional confirmation checkbox).
- **Req 3 (No manual empty revision):** Users must not be able to manually create an empty revision. Revision creation must occur only via the IFC ingestion path (/upload-ifc + ingestion service).

## 3. Out of Scope (Strict Constraints)

- Do not add graph traversal or AGE Cypher for revision search; use relational queries on the revision table only.
- Do not introduce any GraphQL mutation or REST endpoint that creates a revision without IFC ingestion.
- Keep UUID string identifiers and existing schema; do not couple this feature to geometry or BYTEA columns.

## 4. Success Criteria

- [ ] With an active project selected, users can search revisions by author, ifc_filename, commit_message, or created_at and see filtered results.
- [ ] Import IFC modal clearly states that importing creates a new revision.
- [ ] No UI or API path allows creating an empty revision; regression coverage exists to enforce this.
