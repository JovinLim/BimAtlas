Project BimAtlas {
database_type: 'PostgreSQL'
Note: 'Unified Hybrid Relational-Graph Database Schema with Dynamic Filter Sets'
}

// -----------------------------------------------------------------------------
// ENUMS
// -----------------------------------------------------------------------------

Enum merge_status {
Draft
Previewing
Conflict
Ready
Merged
Closed
}

Enum conflict_type {
Attribute_Mismatch
Geometry_Mismatch
Topology_Mismatch
Deleted_vs_Modified
}

Enum resolution_status {
Unresolved
Source_Wins
Target_Wins
Manual_Merge
}

Enum rule_severity {
Error
Warning
Info
}

Enum logic_operator {
AND
OR
}

// -----------------------------------------------------------------------------
// SCHEMA & VALIDATION RULES
// -----------------------------------------------------------------------------

Table ifc_schema {
schema_id UUID [pk]
version_name varchar [note: "e.g., 'IFC4', 'IFC4.3'"]
}

Table validation_rule {
rule_id UUID [pk]
name varchar
description text
schema_id UUID [null, note: "Base rule for the whole IFC schema"]
project_id UUID [null, note: "Custom rule specific to a project"]
target_ifc_class varchar [note: "e.g., 'IfcWall'"]
rule_schema jsonb [note: "JSON Schema definition for validation"]
severity rule_severity
is_active boolean
}

// -----------------------------------------------------------------------------
// PROJECT & VERSION CONTROL HIERARCHY
// -----------------------------------------------------------------------------

Table project {
project_id UUID [pk]
name varchar
description text
}

Table project_schema {
project_id UUID [pk]
schema_id UUID [pk]
Note: 'Junction table: a project can have multiple IFC schemas applied'
}

Table branch {
branch_id UUID [pk]
project_id UUID
name varchar
is_active boolean
}

Table revision {
revision_id UUID [pk]
branch_id UUID
parent_revision_id UUID [null]
created_at timestamp
author_id varchar
commit_message text
}

// -----------------------------------------------------------------------------
// TEMPORAL ENTITY TABLE (Unified Core)
// -----------------------------------------------------------------------------

Table ifc_entity {
entity_id UUID [pk, note: "Unique ID for this specific state/version"]
branch_id UUID
ifc_global_id varchar [note: "Indexed. The persistent identity from IfcRoot"]
ifc_class varchar [note: "e.g., 'IfcWall', 'IfcPropertySet'"]
attributes jsonb [note: "EXPRESS attributes, flattened properties, and entity_refs"]
geometry bytea [null]
created_in_revision_id UUID
obsoleted_in_revision_id UUID [null, note: "NULL means active state"]
}

// -----------------------------------------------------------------------------
// DYNAMIC FILTER SETS (FEAT-001)
// -----------------------------------------------------------------------------

Table filter_sets {
filter_set_id UUID [pk]
branch_id UUID [note: "The branch this filter set belongs to"]
name varchar [note: "e.g., '2HR Fire Rated Walls'"]
logic logic_operator [default: 'AND', note: "Intra-set logic between the JSONB filters"]
filters jsonb [default: '[]', note: "Array of filter conditions"]
color varchar [default: '#4A90D9', note: "Hex color for viewer coloring"]
created_at timestamp
updated_at timestamp
Note: 'Named, reusable filter collections scoped to a branch'
}

Table branch_applied_filter_sets {
branch_id UUID [pk]
filter_set_id UUID [pk]
combination_logic logic_operator [default: 'AND', note: "How this set combines with other applied sets"]
display_order integer [default: 0, note: "Order for color priority; lower = higher priority"]
applied_at timestamp
Note: 'Junction table tracking which filter sets are currently active on a branch'
}

// -----------------------------------------------------------------------------
// SHEET TEMPLATES (FEAT-003 table page bottom-sheet persistence)
// -----------------------------------------------------------------------------

Table sheet_template {
sheet_template_id UUID [pk]
project_id UUID [note: "Project this template belongs to"]
name varchar [note: "Required display name; unique per project"]
sheet jsonb [note: "Active-sheet payload: entries, formulas, lockedIds"]
open boolean [note: "Whether this template is open"]
created_at timestamp
updated_at timestamp
Note: 'Project-scoped bottom-sheet table state for /table page save/load'
}

// -----------------------------------------------------------------------------
// MERGE REQUESTS & CONFLICT RESOLUTION
// -----------------------------------------------------------------------------

Table merge_request {
merge_request_id UUID [pk]
project_id UUID
source_branch_id UUID
target_branch_id UUID
status merge_status
created_by varchar
created_at timestamp
}

Table merge_conflict_log {
log_id UUID [pk]
merge_request_id UUID
ifc_global_id varchar
source_entity_id UUID [null]
target_entity_id UUID [null]
conflict_type conflict_type
resolution_status resolution_status
resolved_entity_id UUID [null]
}

// -----------------------------------------------------------------------------
// RELATIONSHIPS (FOREIGN KEYS)
// -----------------------------------------------------------------------------

Ref: validation_rule.schema_id > ifc_schema.schema_id
Ref: validation_rule.project_id > project.project_id
Ref: project_schema.project_id > project.project_id
Ref: project_schema.schema_id > ifc_schema.schema_id

Ref: branch.project_id > project.project_id
Ref: revision.branch_id > branch.branch_id
Ref: revision.parent_revision_id - revision.revision_id

Ref: ifc_entity.branch_id > branch.branch_id
Ref: ifc_entity.created_in_revision_id > revision.revision_id
Ref: ifc_entity.obsoleted_in_revision_id > revision.revision_id

// Filter Set Relationships
Ref: filter_sets.branch_id > branch.branch_id
Ref: branch_applied_filter_sets.branch_id > branch.branch_id
Ref: branch_applied_filter_sets.filter_set_id > filter_sets.filter_set_id

Ref: sheet_template.project_id > project.project_id

Ref: merge_request.project_id > project.project_id
Ref: merge_request.source_branch_id > branch.branch_id
Ref: merge_request.target_branch_id > branch.branch_id

Ref: merge_conflict_log.merge_request_id > merge_request.merge_request_id
Ref: merge_conflict_log.source_entity_id > ifc_entity.entity_id
Ref: merge_conflict_log.target_entity_id > ifc_entity.entity_id
Ref: merge_conflict_log.resolved_entity_id > ifc_entity.entity_id
