"""The triage JSON contract: fields, coercions, and validation.

Schemas fail closed: anything the desk cannot validate is rejected locally (and
the deterministic fallback takes over) rather than passed to an operator. Only
whitelisted fields survive parsing, so the model cannot smuggle in keys such as
"escalated", "action" or "source" — those are set by the rules layer.
"""

from __future__ import annotations

import json
import math
from typing import Any

from .config import TRIAGE_CATEGORIES

REQUIRED = ["category", "severity", "summary", "suggested_resolution", "confidence"]
OPTIONAL = ["refund_request", "amount_at_risk"]
# Type expectations per field; tuples mark accepted alternatives.
TYPES: dict[str, type | tuple[type, type]] = {
    "category": str,
    "severity": str,
    "summary": str,
    "suggested_resolution": str,
    "confidence": (int, float),
}
VALID_SEVERITY = {"low", "medium", "high"}


def parse(raw: str) -> dict[str, Any]:
    """Parse a model answer; raise ValueError listing every broken expectation."""
    try:
        decision = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Answer is not valid JSON: {exc}") from exc
    if not isinstance(decision, dict):
        raise ValueError("Answer is not a JSON object")

    errors: list[str] = []
    for field in REQUIRED:
        value = decision.get(field)
        if field not in decision:
            errors.append(f"missing field: {field}")
        elif isinstance(value, bool) or not isinstance(value, TYPES[field]):
            errors.append(f"field {field} has wrong type: {type(value).__name__}")
    if errors:
        raise ValueError("; ".join(errors))

    decision = _audit(decision, errors)
    if errors:
        raise ValueError("; ".join(errors))
    return {key: decision[key] for key in REQUIRED + OPTIONAL}


def _audit(decision: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    """Coerce, normalize and whitelist-check the fields the schema knows about."""
    # category falls within the operational taxonomy (case/space-insensitive).
    declared = str(decision.get("category", "")).strip().lower().replace(" ", "_")
    if declared not in TRIAGE_CATEGORIES:
        errors.append(f"unknown category: {declared!r}")
    else:
        decision["category"] = declared

    # Stored normalized: downstream rules compare against lowercase values.
    severity = str(decision.get("severity", "")).strip().lower()
    if severity not in VALID_SEVERITY:
        errors.append(f"severity must be one of {sorted(VALID_SEVERITY)}")
    else:
        decision["severity"] = severity

    confidence = float(decision["confidence"])
    if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
        errors.append("confidence out of range [0,1]")
    decision["confidence"] = confidence

    refund = decision.get("refund_request")
    decision["refund_request"] = (
        refund
        if isinstance(refund, bool)
        else (str(refund).strip().lower() in ("true", "yes", "1") if refund is not None else False)
    )

    amount = decision.get("amount_at_risk", 0.0)
    try:
        if isinstance(amount, bool):
            raise TypeError("boolean amount")
        amount = float(amount)
    except (TypeError, ValueError):
        errors.append("amount_at_risk is not numeric")
        amount = 0.0
    if not math.isfinite(amount) or amount < 0:
        errors.append("amount_at_risk must be a finite number >= 0")
        amount = 0.0
    decision["amount_at_risk"] = round(amount, 2)

    decision["summary"] = str(decision["summary"]).strip()
    decision["suggested_resolution"] = str(decision["suggested_resolution"]).strip()
    return decision
