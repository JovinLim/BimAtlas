"""Validation engine: evaluates IfcValidation rules against a branch/revision.

The engine fetches rules linked to a schema via the AGE graph, resolves
target entities (with optional inheritance expansion and subgraph scoping),
and applies attribute-level condition checks in Python.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from ...db import (
    create_validation_entity,
    create_validation_revision,
    fetch_validation_entity,
    get_latest_revision_seq,
)
from ...schema import ifc_schema_loader
from ..graph.age_client import (
    get_entities_connected_via,
    get_entities_in_aggregate_scope,
    get_entities_in_spatial_scope,
    get_rules_for_schema,
)

logger = logging.getLogger("bimatlas.validation")


# ---------------------------------------------------------------------------
# Result data classes
# ---------------------------------------------------------------------------


@dataclass
class Violation:
    global_id: str
    ifc_class: str
    message: str


@dataclass
class RuleResult:
    rule_global_id: str
    rule_name: str
    severity: str
    passed: bool
    violations: list[Violation] = field(default_factory=list)


@dataclass
class ValidationRunResult:
    schema_global_id: str
    schema_name: str
    branch_id: str
    revision_seq: int
    results: list[RuleResult] = field(default_factory=list)
    summary: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Attribute check operators
# ---------------------------------------------------------------------------


def _resolve_nested_value(attributes: dict, path: str) -> Any:
    """Walk a dotted path into nested dicts. Returns ``_MISSING`` sentinel if absent."""
    parts = path.split(".")
    current: Any = attributes
    for part in parts:
        if isinstance(current, dict):
            if part in current:
                current = current[part]
            else:
                return _MISSING
        else:
            return _MISSING
    return current


_MISSING = object()


def _op_equals(actual: Any, expected: str) -> bool:
    if actual is _MISSING or actual is None:
        return False
    return str(actual).lower() == str(expected).lower()


def _op_not_equals(actual: Any, expected: str) -> bool:
    if actual is _MISSING or actual is None:
        return True
    return str(actual).lower() != str(expected).lower()


def _op_contains(actual: Any, expected: str) -> bool:
    if actual is _MISSING or actual is None:
        return False
    if isinstance(actual, list):
        return expected in [str(v) for v in actual]
    return expected.lower() in str(actual).lower()


def _op_exists(actual: Any, _expected: str | None = None) -> bool:
    return actual is not _MISSING and actual is not None


def _op_not_exists(actual: Any, _expected: str | None = None) -> bool:
    return actual is _MISSING or actual is None


def _op_greater_than(actual: Any, expected: str) -> bool:
    try:
        return float(actual) > float(expected)
    except (TypeError, ValueError):
        return False


def _op_less_than(actual: Any, expected: str) -> bool:
    try:
        return float(actual) < float(expected)
    except (TypeError, ValueError):
        return False


def _op_matches(actual: Any, pattern: str) -> bool:
    if actual is _MISSING or actual is None:
        return False
    try:
        return bool(re.search(pattern, str(actual)))
    except re.error:
        return False


_OPERATORS: dict[str, Any] = {
    "equals": _op_equals,
    "not_equals": _op_not_equals,
    "contains": _op_contains,
    "exists": _op_exists,
    "not_exists": _op_not_exists,
    "greater_than": _op_greater_than,
    "less_than": _op_less_than,
    "matches": _op_matches,
}


# ---------------------------------------------------------------------------
# Core evaluation
# ---------------------------------------------------------------------------


def _resolve_target_classes(rule_attrs: dict) -> list[str]:
    """Resolve target IFC classes, expanding subtypes when requested."""
    target_class = rule_attrs.get("TargetClass", "")
    include_subtypes = rule_attrs.get("IncludeSubtypes", False)

    if not target_class:
        return []

    if include_subtypes:
        try:
            descendants = ifc_schema_loader.get_descendants(
                target_class, include_self=True, concrete_only=True,
            )
            return descendants if descendants else [target_class]
        except Exception:
            return [target_class]

    return [target_class]


def _resolve_scoped_entities(
    rule_attrs: dict,
    rev: int,
    branch_id: str,
) -> list[str] | None:
    """Apply spatial context scoping via graph traversal. Returns global_ids or None."""
    spatial_ctx = rule_attrs.get("SpatialContext")
    if not spatial_ctx or not isinstance(spatial_ctx, dict):
        return None

    traversal = spatial_ctx.get("traversal", "")
    scope_gid = spatial_ctx.get("scope_global_id")
    scope_name = spatial_ctx.get("scope_name")

    if traversal == "IfcRelContainedInSpatialStructure":
        return get_entities_in_spatial_scope(scope_gid, scope_name, rev, branch_id)
    elif traversal == "IfcRelAggregates":
        if scope_gid:
            return get_entities_in_aggregate_scope(scope_gid, rev, branch_id)
    elif traversal in (
        "IfcRelConnectsElements", "IfcRelVoidsElement",
        "IfcRelFillsElement", "IfcRelDefinesByType",
    ):
        if scope_gid:
            return get_entities_connected_via(scope_gid, traversal, rev, branch_id)

    return None


def _check_conditions(
    entity_attrs: dict, conditions: list[dict],
) -> str | None:
    """Evaluate conditions against entity attributes. Returns failure message or None."""
    for cond in conditions:
        path = cond.get("path", "")
        operator = cond.get("operator", "exists")
        expected = cond.get("value")

        op_fn = _OPERATORS.get(operator)
        if op_fn is None:
            return f"Unknown operator: {operator}"

        actual = _resolve_nested_value(entity_attrs, path)

        if operator in ("exists", "not_exists"):
            if not op_fn(actual):
                return f"{path}: expected {operator}"
        else:
            if not op_fn(actual, expected):
                actual_display = actual if actual is not _MISSING else "<missing>"
                return f"{path}: {actual_display} {operator} {expected} failed"

    return None


def evaluate_rule(
    rule_global_id: str,
    rule_attrs: dict,
    branch_id: str,
    rev: int,
) -> RuleResult:
    """Evaluate a single validation rule against entities on a branch/revision."""
    rule_name = rule_attrs.get("Name", "Unnamed rule")
    severity = rule_attrs.get("Severity", "Error")
    conditions = rule_attrs.get("Conditions", [])

    if not isinstance(conditions, list):
        conditions = []

    target_classes = _resolve_target_classes(rule_attrs)
    if not target_classes:
        return RuleResult(
            rule_global_id=rule_global_id,
            rule_name=rule_name,
            severity=severity,
            passed=True,
        )

    scoped_gids = _resolve_scoped_entities(rule_attrs, rev, branch_id)

    from ...db import fetch_entities_at_revision
    all_entities: list[dict] = []
    for tc in target_classes:
        rows = fetch_entities_at_revision(rev, branch_id, ifc_class=tc)
        all_entities.extend(rows)

    if scoped_gids is not None:
        scoped_set = set(scoped_gids)
        all_entities = [
            e for e in all_entities if e.get("ifc_global_id") in scoped_set
        ]

    # Deduplicate by global_id
    seen: set[str] = set()
    unique_entities: list[dict] = []
    for e in all_entities:
        gid = e.get("ifc_global_id", "")
        if gid not in seen:
            seen.add(gid)
            unique_entities.append(e)

    violations: list[Violation] = []
    for entity in unique_entities:
        attrs = entity.get("attributes", {})
        if isinstance(attrs, str):
            import json
            attrs = json.loads(attrs)

        failure_msg = _check_conditions(attrs, conditions)
        if failure_msg:
            violations.append(Violation(
                global_id=entity.get("ifc_global_id", ""),
                ifc_class=entity.get("ifc_class", ""),
                message=failure_msg,
            ))

    return RuleResult(
        rule_global_id=rule_global_id,
        rule_name=rule_name,
        severity=severity,
        passed=len(violations) == 0,
        violations=violations,
    )


def run_validation(
    schema_global_id: str,
    branch_id: str,
    revision_seq: int | None = None,
    persist_result: bool = True,
) -> ValidationRunResult:
    """Execute all rules in a validation schema against a branch."""
    if revision_seq is None:
        revision_seq = get_latest_revision_seq(branch_id)
        if revision_seq is None:
            raise ValueError("No revisions on branch")

    schema_entity = fetch_validation_entity(branch_id, schema_global_id)
    if schema_entity is None:
        raise ValueError(f"Schema {schema_global_id} not found")

    schema_attrs = schema_entity.get("attributes", {})
    if isinstance(schema_attrs, str):
        import json
        schema_attrs = json.loads(schema_attrs)

    schema_name = schema_attrs.get("Name", "Unnamed schema")

    rule_gids = get_rules_for_schema(schema_global_id, revision_seq, branch_id)

    results: list[RuleResult] = []
    for rule_gid in rule_gids:
        rule_entity = fetch_validation_entity(branch_id, rule_gid)
        if rule_entity is None:
            logger.warning("Rule %s not found in DB, skipping", rule_gid)
            continue

        rule_attrs = rule_entity.get("attributes", {})
        if isinstance(rule_attrs, str):
            import json
            rule_attrs = json.loads(rule_attrs)

        result = evaluate_rule(rule_gid, rule_attrs, branch_id, revision_seq)
        results.append(result)

    errors = sum(1 for r in results if not r.passed and r.severity == "Error")
    warnings = sum(1 for r in results if not r.passed and r.severity == "Warning")
    info = sum(1 for r in results if not r.passed and r.severity == "Info")
    passed = sum(1 for r in results if r.passed)

    summary = {"errors": errors, "warnings": warnings, "info": info, "passed": passed}

    run_result = ValidationRunResult(
        schema_global_id=schema_global_id,
        schema_name=schema_name,
        branch_id=branch_id,
        revision_seq=revision_seq,
        results=results,
        summary=summary,
    )

    if persist_result:
        try:
            result_attrs = {
                "Name": f"Validation run: {schema_name}",
                "Description": f"Results for schema {schema_global_id}",
                "SchemaGlobalId": schema_global_id,
                "SchemaName": schema_name,
                "Summary": summary,
                "Results": [
                    {
                        "rule_global_id": r.rule_global_id,
                        "rule_name": r.rule_name,
                        "severity": r.severity,
                        "passed": r.passed,
                        "violation_count": len(r.violations),
                        "violations": [
                            {"global_id": v.global_id, "ifc_class": v.ifc_class,
                             "message": v.message}
                            for v in r.violations
                        ],
                    }
                    for r in results
                ],
            }
            rev_info = create_validation_revision(branch_id, f"Validation run: {schema_name}")
            create_validation_entity(
                branch_id, rev_info["revision_id"],
                "IfcValidationResult", result_attrs,
            )
        except Exception:
            logger.exception("Failed to persist validation result")

    return run_result
