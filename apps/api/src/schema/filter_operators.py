"""
Canonical operator vocabulary and per-mode semantics for FEAT-001 filter sets.

Shared contract between API (SQL translation) and frontend (UI). All operators
are normalized to snake_case. Legacy filters without an operator field use
backward-compat defaults.
"""

from typing import Final

# ---------------------------------------------------------------------------
# String & logical operators (attribute mode)
# ---------------------------------------------------------------------------
STRING_OPERATORS: Final[frozenset[str]] = frozenset({
    "is",           # Exact match (case-insensitive by default)
    "is_not",       # Not equal
    "contains",     # Substring search (ILIKE %value%)
    "not_contains", # Does not contain
    "starts_with",  # Prefix match
    "ends_with",    # Suffix match
    "is_empty",     # Null or empty string (no value required)
    "is_not_empty", # Has non-empty value (no value required)
})

# ---------------------------------------------------------------------------
# Numeric operators (attribute mode, value_type="numeric")
# ---------------------------------------------------------------------------
NUMERIC_OPERATORS: Final[frozenset[str]] = frozenset({
    "equals",       # ==
    "not_equals",  # !=
    "gt",           # >
    "lt",           # <
    "gte",          # >=
    "lte",          # <=
})

# ---------------------------------------------------------------------------
# Class mode operators
# ---------------------------------------------------------------------------
CLASS_OPERATORS: Final[frozenset[str]] = frozenset({
    "is",           # Exact class match (default)
    "is_not",       # Exclude exact class
    "inherits_from", # Class + all descendants in IFC hierarchy
})

# ---------------------------------------------------------------------------
# Relation mode: no operator (relation type is the filter)
# ---------------------------------------------------------------------------

# All valid operators across modes
ALL_OPERATORS: Final[frozenset[str]] = (
    STRING_OPERATORS | NUMERIC_OPERATORS | CLASS_OPERATORS
)

# Operators that do not require a value
VALUE_OPTIONAL_OPERATORS: Final[frozenset[str]] = frozenset({
    "is_empty",
    "is_not_empty",
})


def get_default_operator(mode: str) -> str:
    """Return backward-compat default when operator is missing."""
    if mode == "class":
        return "is"
    if mode == "attribute":
        return "contains"  # Legacy: ILIKE %value%
    return "is"  # relation has no operator; fallback unused


def normalize_logic(logic: str | None) -> str:
    """Return allowlisted logic token (AND/OR)."""
    if logic and str(logic).upper() in ("AND", "OR"):
        return str(logic).upper()
    return "AND"


def is_valid_operator(mode: str, operator: str | None) -> bool:
    """Check if operator is valid for the given mode."""
    if not operator:
        return True  # Will use default
    if mode == "class":
        return operator in CLASS_OPERATORS
    if mode == "attribute":
        return operator in STRING_OPERATORS or operator in NUMERIC_OPERATORS
    if mode == "relation":
        return True  # No operator used
    return False


def resolve_operator(f: dict) -> str:
    """Resolve effective operator from filter dict, applying defaults."""
    op = f.get("operator") or f.get("op")
    if op and isinstance(op, str):
        return op.strip().lower()
    mode = f.get("mode") or "attribute"
    default = get_default_operator(mode)
    if mode == "attribute":
        value_type = (f.get("valueType") or f.get("value_type") or "string").lower()
        if value_type == "numeric":
            return "equals"
    return default


def value_required_for_operator(operator: str) -> bool:
    """Return True if the operator requires a value."""
    return operator not in VALUE_OPTIONAL_OPERATORS
