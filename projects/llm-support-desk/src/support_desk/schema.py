"""The triage JSON contract: fields, coercions, and validation.

Schemas fail closed: anything the desk cannot validate is rejected locally (
and the deterministic rules take over) rather than passed to an operator.
"""

from __future__ import annotations

from typing import Any

from .config import TRIAGE_CATEGORIES

REQUIRED = ["category", "severity", "summary", "suggested_resolution", "confidence"]
TYPES = {"category": str, "severity": str, "summary": str,
         "suggested_resolution": str, "confidence": (int, float)}
VALID_SEVERITY = {"low", "medium", "high"}


def parse(raw: str) -> dict[str, Any]:
    """Parse a model answer; raise ValueError listing every broken expectation."""
    import json

    try:
        decision = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Answer is not valid JSON: {exc}") from exc
    if not isinstance(decision, dict):
        raise ValueError("Answer is not a JSON object")

    errors: list[str] = []
    for field in REQUIRED:
        if field not in decision:
            errors.append(f"missing field: {field}")
        elif not isinstance(decision[field], TYPES[field]):
            errors.append(f"field {field} has wrong type: {type(decision[field]).__name__}")
    if errors:
        raise ValueError("; ".join(errors))

    decision = _audit(decision, errors)
    if errors:
        raise ValueError("; ".join(errors))
    return decision


def _audit(decision: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    """Coerce and whitelist-check fields the schema knows about."""
    # category falls within the operational taxonomy (typo-tolerant).
    declared = str(decision.get("category", "")).strip().lower().replace(" ", "_")
    if declared not in TRIAGE_CATEGORIES:
        errors.append(f"unknown category: {declared!r}")
    else:
        decision["category"] = declared

    if str(decision.get("severity", "")).lower() not in VALID_SEVERITY:
        errors.append(f"severity must be one of {sorted(VALID_SEVERITY)}")

    try:
        decision["confidence"] = float(decision["confidence"])
    except (KeyError, TypeError, ValueError):
        errors.append("confidence is not numeric")
    else:
        if not 0.0 <= decision["confidence"] <= 1.0:
            errors.append("confidence out of range [0,1]")

    refund = decision.get("refund_request")
    decision["refund_request"] = bool(refund) if isinstance(refund, bool) else (
        str(refund).strip().lower() in ("true", "yes", "1") if refund is not None else False
    )

    try:
        decision["amount_at_risk"] = round(float(decision.get("amount_at_risk", 0.0)), 2)
    except (TypeError, ValueError):
        decision["amount_at_risk"] = 0.0

    decision["summary"] = str(decision["summary"]).strip()
    decision["suggested_resolution"] = str(decision["suggested_resolution"]).strip()
    return decision
