# Filter Logic Tree Specification

Canonical contract for nested Match ALL / Match ANY filter logic stored in JSONB.

## Max Depth Rule

- **Root (depth 0):** Single group node. Required.
- **Sub-group (depth 1):** Optional nested groups. Max one level of nesting.
- **Leaf (depth 2 max):** Individual filter conditions. May appear at depth 1 (direct children of root) or depth 2 (children of a sub-group).

```
Root Group (depth 0)
├── Leaf A (depth 1)
├── Leaf B (depth 1)
└── Sub-group (depth 1)
    ├── Leaf C (depth 2)
    └── Leaf D (depth 2)
```

## Canonical JSON Schema

### Group Node

```json
{
  "kind": "group",
  "op": "ALL" | "ANY",
  "children": [ /* FilterGroupNode | FilterLeafNode */ ]
}
```

- `kind`: Must be `"group"`.
- `op`: `"ALL"` (Match ALL of the following) or `"ANY"` (Match ANY of the following).
- `children`: Non-empty array of group or leaf nodes. At depth 1, may contain leaves or one sub-group. At depth 2, may contain leaves only.

### Leaf Node (Class Mode)

```json
{
  "kind": "leaf",
  "mode": "class",
  "ifcClass": "IfcWall",
  "operator": "is" | "is_not" | "inherits_from"
}
```

### Leaf Node (Attribute Mode)

```json
{
  "kind": "leaf",
  "mode": "attribute",
  "attribute": "Name",
  "operator": "is" | "contains" | "gt" | ...,
  "value": "value",
  "valueType": "string" | "numeric" | "object"
}
```

### Leaf Node (Relation Mode)

```json
{
  "kind": "leaf",
  "mode": "relation",
  "relation": "IfcRelContainedInSpatialStructure",
  "relationTargetClass": "IfcBuildingStorey",
  "relationTargetAttribute": "Name",
  "relationTargetOperator": "contains",
  "relationTargetValue": "Ground",
  "relationTargetValueType": "string"
}
```

### Root Expression Shape

The `filter_sets.filters` JSONB column stores:

- **Canonical (tree):** `{ "kind": "group", "op": "ALL" | "ANY", "children": [...] }`
- **Legacy (flat):** `[ { "mode": "class", ... }, ... ]` — treated as array of leaf conditions.

## Legacy Compatibility

When `filters` is an array (legacy flat payload):

```json
[
  { "mode": "class", "ifcClass": "IfcWall", "operator": "is" },
  { "mode": "attribute", "attribute": "Name", "operator": "contains", "value": "Door" }
]
```

Auto-wrap as:

```json
{
  "kind": "group",
  "op": "ALL",
  "children": [
    { "kind": "leaf", "mode": "class", "ifcClass": "IfcWall", "operator": "is" },
    { "kind": "leaf", "mode": "attribute", "attribute": "Name", "operator": "contains", "value": "Door" }
  ]
}
```

The `logic` field on the filter set (`AND`/`OR`) maps to `op`: `AND` → `ALL`, `OR` → `ANY`.

## Operator Mapping

| UI term | Legacy | Canonical |
|---------|--------|-----------|
| Match ALL | AND | ALL |
| Match ANY | OR | ANY |

## Examples

### Example 1: Simple ALL (single level)

```json
{
  "kind": "group",
  "op": "ALL",
  "children": [
    { "kind": "leaf", "mode": "class", "ifcClass": "IfcWall", "operator": "is" },
    { "kind": "leaf", "mode": "attribute", "attribute": "Name", "operator": "contains", "value": "2HR", "valueType": "string" }
  ]
}
```

### Example 2: Nested ANY inside ALL

```json
{
  "kind": "group",
  "op": "ALL",
  "children": [
    { "kind": "leaf", "mode": "class", "ifcClass": "IfcWall", "operator": "is" },
    {
      "kind": "group",
      "op": "ANY",
      "children": [
        { "kind": "leaf", "mode": "attribute", "attribute": "Name", "operator": "contains", "value": "Core", "valueType": "string" },
        { "kind": "leaf", "mode": "attribute", "attribute": "Tag", "operator": "is", "value": "A1", "valueType": "string" }
      ]
    }
  ]
}
```

### Example 3: ALL of (Set A, Set B) OR ANY of (Set C, Set D)

This is **inter-set** logic (applied to multiple filter sets). The `branch_applied_filter_sets` junction table still uses `combination_logic` for that. Each filter set itself stores a tree in `filters`; the inter-set logic is unchanged.

## Validation Rules

1. Root must be a group with `kind: "group"` and `op` in `["ALL", "ANY"]`.
2. `children` must be non-empty for groups.
3. Max depth: 2. Root = 0, sub-group = 1, leaf = 2.
4. At depth 2, only leaf nodes allowed.
5. Leaf nodes require `kind: "leaf"` and valid `mode` + operator/value fields per mode.
6. Empty groups are invalid.

## API Contract

- **GraphQL input:** Accept `FilterExpressionInput` (JSON scalar or structured input) for create/update filter set mutations.
- **GraphQL output:** Return `filters` as JSON (tree or legacy array for compatibility).
- **Deprecated:** `AND`/`OR` in API docs; use `Match ALL` / `Match ANY` in UI copy only.
