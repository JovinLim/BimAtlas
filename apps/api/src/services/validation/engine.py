"""Validation engine: evaluates validation_rule rows against a branch/revision.

Uses the ``validation_rule`` table (linked to ``ifc_schema``) as the source
of truth for rule definitions. Results are persisted as ``IfcValidationResult``
entities in ``ifc_entity`` for branch/revision-scoped history.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from ...db import (
    create_validation_entity,
    fetch_entities_at_revision,
    fetch_ifc_schema_by_id,
    fetch_validation_rules_by_schema_id,
    get_latest_revision_seq,
    get_revision_id_for_seq,
    has_validation_results_for_schema_revision,
    refresh_mv_entity_validations,
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
    failed_global_ids: list[str] = field(default_factory=list)
    passed_global_ids: list[str] = field(default_factory=list)


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


def _resolve_target_classes(
    target_ifc_class: str,
    include_inherited: bool,
) -> list[str]:
    """Return [target_class] or [target_class] + descendant classes for entity fetch."""
    if not include_inherited:
        return [target_ifc_class]
    try:
        from ...schema import ifc_schema_loader
        descendants = ifc_schema_loader.get_descendants(
            target_ifc_class,
            include_self=False,
            concrete_only=False,
        )
        return [target_ifc_class] + descendants
    except Exception:
        return [target_ifc_class]


def run_validation_by_uploaded_schema(
    schema_id: str,
    branch_id: str,
    revision_seq: int | None = None,
) -> ValidationRunResult:
    """Execute validation rules from an uploaded IFC schema against a branch.

    Uses validation_rule rows (required_attributes, inheritance) linked to
    the schema. Each rule may set includeSubclasses in its rule_schema:
    when True, the rule applies to the target IFC class and all its
    subclasses; when False, only the exact target class is considered.
    """
    import json

    if revision_seq is None:
        revision_seq = get_latest_revision_seq(branch_id)
        if revision_seq is None:
            raise ValueError("No revisions on branch")

    # Enforce: a given validation schema can only be run once per
    # IFC model revision on a branch.
    if has_validation_results_for_schema_revision(branch_id, schema_id, revision_seq):
        raise ValueError(
            f"Validation schema {schema_id} has already been run for "
            f"revision {revision_seq} on branch {branch_id}"
        )

    schema_row = fetch_ifc_schema_by_id(schema_id)
    if schema_row is None:
        raise ValueError(f"Uploaded schema {schema_id} not found")
    schema_name = schema_row.get("version_name", "Unknown")

    rule_rows = fetch_validation_rules_by_schema_id(schema_id)
    if not rule_rows:
        return ValidationRunResult(
            schema_global_id=schema_id,
            schema_name=schema_name,
            branch_id=branch_id,
            revision_seq=revision_seq,
            results=[],
            summary={"errors": 0, "warnings": 0, "info": 0, "passed": 0},
        )

    results: list[RuleResult] = []
    for row in rule_rows:
        rule_id = str(row.get("rule_id", ""))
        rule_name = row.get("name", "Unnamed rule")
        severity = row.get("severity", "Error") or "Error"
        target_class = row.get("target_ifc_class", "")
        payload = row.get("rule_schema")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (TypeError, ValueError, json.JSONDecodeError):
                results.append(
                    RuleResult(
                        rule_global_id=rule_id,
                        rule_name=rule_name,
                        severity=severity,
                        passed=True,
                    )
                )
                continue
        if not isinstance(payload, dict):
            results.append(
                RuleResult(
                    rule_global_id=rule_id,
                    rule_name=rule_name,
                    severity=severity,
                    passed=True,
                )
            )
            continue

        rule_type = payload.get("ruleType")
        conditions = payload.get("Conditions") or []
        condition_logic = payload.get("ConditionLogic", "AND")
        include_subclasses = bool(payload.get("includeSubclasses", False))
        if not isinstance(conditions, list):
            conditions = []

        if rule_type == "attribute_check" and conditions:
            target_classes = _resolve_target_classes(
                target_class, include_subclasses,
            )
            entities = fetch_entities_at_revision(
                revision_seq, branch_id, ifc_classes=target_classes,
            )
            violations: list[Violation] = []
            for entity in entities:
                attrs = entity.get("attributes", {})
                if isinstance(attrs, str):
                    try:
                        attrs = json.loads(attrs)
                    except (TypeError, ValueError, json.JSONDecodeError):
                        attrs = {}
                if not isinstance(attrs, dict):
                    attrs = {}
                passed = False
                if condition_logic == "OR":
                    for cond in conditions:
                        path = cond.get("path", "")
                        if not path:
                            continue
                        operator = cond.get("operator", "exists")
                        expected = cond.get("value")
                        op_fn = _OPERATORS.get(operator)
                        if not op_fn:
                            continue
                        actual = _resolve_nested_value(attrs, path)
                        cond_ok = (
                            op_fn(actual) if operator in ("exists", "not_exists")
                            else op_fn(actual, expected or "")
                        )
                        if cond_ok:
                            passed = True
                            break
                else:
                    passed = _check_conditions(attrs, conditions) is None
                if not passed:
                    fail_msg = _check_conditions(attrs, conditions)
                    violations.append(
                        Violation(
                            global_id=entity.get("ifc_global_id", ""),
                            ifc_class=entity.get("ifc_class", ""),
                            message=fail_msg or "Condition check failed",
                        )
                    )
            failed = [v.global_id for v in violations]
            passed_gids = [
                e.get("ifc_global_id", "")
                for e in entities
                if e.get("ifc_global_id") and e.get("ifc_global_id") not in set(failed)
            ]
            results.append(
                RuleResult(
                    rule_global_id=rule_id,
                    rule_name=rule_name,
                    severity=severity,
                    passed=len(violations) == 0,
                    violations=violations,
                    failed_global_ids=failed,
                    passed_global_ids=passed_gids,
                )
            )
        elif rule_type == "required_attributes":
            required_attrs = payload.get("effectiveRequiredAttributes") or []
            if not isinstance(required_attrs, list):
                required_attrs = []
            attr_names = [
                a.get("name") for a in required_attrs
                if isinstance(a, dict) and a.get("name")
            ]
            target_classes = _resolve_target_classes(
                target_class, include_subclasses,
            )
            entities = fetch_entities_at_revision(
                revision_seq, branch_id, ifc_classes=target_classes,
            )
            violations = []
            for entity in entities:
                attrs = entity.get("attributes", {})
                if isinstance(attrs, str):
                    try:
                        attrs = json.loads(attrs)
                    except (TypeError, ValueError, json.JSONDecodeError):
                        attrs = {}
                if not isinstance(attrs, dict):
                    attrs = {}
                for attr_name in attr_names:
                    val = _resolve_nested_value(attrs, attr_name)
                    if val is _MISSING or val is None:
                        violations.append(
                            Violation(
                                global_id=entity.get("ifc_global_id", ""),
                                ifc_class=entity.get("ifc_class", ""),
                                message=f"Missing required attribute: {attr_name}",
                            )
                        )
            failed = [v.global_id for v in violations]
            passed_gids = [
                e.get("ifc_global_id", "")
                for e in entities
                if e.get("ifc_global_id") and e.get("ifc_global_id") not in set(failed)
            ]
            results.append(
                RuleResult(
                    rule_global_id=rule_id,
                    rule_name=rule_name,
                    severity=severity,
                    passed=len(violations) == 0,
                    violations=violations,
                    failed_global_ids=failed,
                    passed_global_ids=passed_gids,
                )
            )
        else:
            results.append(
                RuleResult(
                    rule_global_id=rule_id,
                    rule_name=rule_name,
                    severity=severity,
                    passed=True,
                    failed_global_ids=[],
                    passed_global_ids=[],
                )
            )

    errors = sum(1 for r in results if not r.passed and r.severity == "Error")
    warnings = sum(1 for r in results if not r.passed and r.severity == "Warning")
    info = sum(1 for r in results if not r.passed and r.severity == "Info")
    passed = sum(1 for r in results if r.passed)
    summary = {"errors": errors, "warnings": warnings, "info": info, "passed": passed}

    run_result = ValidationRunResult(
        schema_global_id=schema_id,
        schema_name=schema_name,
        branch_id=branch_id,
        revision_seq=revision_seq,
        results=results,
        summary=summary,
    )

    try:
        rev_id = get_revision_id_for_seq(branch_id, revision_seq)
        if rev_id is None:
            logger.warning(
                "No revision_id found for branch %s revision_seq %s; "
                "skipping persistence of validation results",
                branch_id,
                revision_seq,
            )
        else:
            # Persist one IfcValidationResults entity per rule (write-optimized).
            for r in results:
                rule_version_val = 1
                for row in rule_rows:
                    if str(row.get("rule_id", "")) == r.rule_global_id:
                        rule_version_val = int(row.get("version", 1))
                        break
                result_attrs = {
                    "SchemaGlobalId": schema_id,
                    "SchemaName": schema_name,
                    "TargetRevisionSeq": revision_seq,
                    "rule_id": r.rule_global_id,
                    "rule_version": rule_version_val,
                    "RuleName": r.rule_name,
                    "Severity": r.severity,
                    "results": {
                        "failed_global_ids": r.failed_global_ids,
                        "passed_global_ids": r.passed_global_ids,
                    },
                }
                create_validation_entity(
                    branch_id,
                    rev_id,
                    "IfcValidationResults",
                    result_attrs,
                )

            # Also persist legacy IfcValidationResult for backward-compat API.
            legacy_attrs = {
                "Name": f"Validation run: {schema_name}",
                "Description": f"Results for schema {schema_id}",
                "SchemaGlobalId": schema_id,
                "SchemaName": schema_name,
                "TargetRevisionSeq": revision_seq,
                "Summary": summary,
                "Results": [
                    {
                        "rule_global_id": r.rule_global_id,
                        "rule_name": r.rule_name,
                        "severity": r.severity,
                        "passed": r.passed,
                        "violation_count": len(r.violations),
                        "violations": [
                            {"global_id": v.global_id, "ifc_class": v.ifc_class, "message": v.message}
                            for v in r.violations
                        ],
                    }
                    for r in results
                ],
            }
            create_validation_entity(branch_id, rev_id, "IfcValidationResult", legacy_attrs)

            try:
                refresh_mv_entity_validations()
            except Exception:
                logger.warning("Failed to refresh mv_entity_validations", exc_info=True)
    except Exception:
        logger.exception("Failed to persist validation results")

    return run_result
