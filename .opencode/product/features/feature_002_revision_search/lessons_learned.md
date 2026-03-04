## Hard Constraints

- The database schema and API use UUID string identifiers (project_id, branch_id, revision_id); all new code must treat IDs as strings.
- Revision search must use parameterized queries only; no raw user-provided SQL or string interpolation in WHERE clauses.
- Revisions are created only via IFC ingestion (/upload-ifc); no createRevision mutation or equivalent REST endpoint.

## Resolved Pitfalls

- (To be filled as implementation proceeds.)
