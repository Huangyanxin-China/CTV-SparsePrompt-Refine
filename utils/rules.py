"""Utilities for validated, serializable threshold rules."""

from __future__ import annotations

from typing import Any, Mapping


SUPPORTED_THRESHOLD_OPERATORS = {"lt", "ge"}


def threshold_condition(value: float, operator: str, threshold: float) -> bool:
    """Evaluate a supported threshold operator consistently."""
    operator = str(operator)
    if operator == "lt":
        return float(value) < float(threshold)
    if operator == "ge":
        return float(value) >= float(threshold)
    raise ValueError(
        f"Unsupported threshold operator {operator!r}; "
        f"expected one of {sorted(SUPPORTED_THRESHOLD_OPERATORS)}"
    )


def extract_threshold_rule(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Extract and validate a threshold rule from a rule or summary JSON object."""
    if "rule" in payload:
        rule = payload["rule"]
    elif "threshold_rule" in payload:
        rule = payload["threshold_rule"]
    else:
        rule = payload

    if not isinstance(rule, Mapping):
        raise ValueError("Threshold rule must be a JSON object.")

    required = {
        "feature",
        "op",
        "threshold",
        "method_if_true",
        "method_if_false",
    }
    missing = required - set(rule)
    if missing:
        raise ValueError(f"Threshold rule is missing fields: {sorted(missing)}")
    if str(rule["op"]) not in SUPPORTED_THRESHOLD_OPERATORS:
        raise ValueError(
            f"Unsupported threshold operator {rule['op']!r}; "
            f"expected one of {sorted(SUPPORTED_THRESHOLD_OPERATORS)}"
        )
    return dict(rule)
