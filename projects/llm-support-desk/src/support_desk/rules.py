"""Deterministic business-rules layer.

The model may propose; the rules may dispose. Nothing a customer sees is
executed without passing these invariants, regardless of LLM confidence.
"""

from __future__ import annotations

from .config import Config, TRIAGE_CATEGORIES

# Company policy: first-line agents may decide refunds up to this cap.
# Above it, the claim is escalated to a human supervisor.
REFUND_AUTOCAP_MXN = 500.00


def post_validate(decision: dict, ticket_amount: float, cfg: Config) -> dict:
    """Enforce policy invariants on a (validated) model decision."""
    d = dict(decision)

    if d["category"] not in TRIAGE_CATEGORIES:  # defense in depth
        d["category"] = "amount_discrepancy"
        d["confidence"] = min(d.get("confidence", 0.0), 0.4)

    # Refunds: capped. A model suggesting above-cap refunds is overridden.
    if d.get("refund_request") and ticket_amount > REFUND_AUTOCAP_MXN:
        d["suggested_resolution"] = (
            "Escalate to supervisor: refund above first-line cap "
            f"({REFUND_AUTOCAP_MXN:.2f} MXN). " + d["suggested_resolution"]
        )
        d["escalated"] = True

    # Low confidence means no autonomous decisions, only prepared context.
    if d["confidence"] <= cfg.escalation_threshold:
        d["escalated"] = True
        d["suggested_resolution"] = (
            "Hold for human review (model confidence below threshold). "
            "Prepare context: " + d["suggested_resolution"]
        )

    # Unauthorized charges always require action, never auto-closure.
    if d["category"] == "unauthorized_charge" and d.get("severity") == "low":
        d["severity"] = "high"
        d["escalated"] = True

    d.setdefault("escalated", False)
    return d


# -------------------------------------------------------------------------- #
# Deterministic fallback classifier: keyword-driven, auditable by hand.      #
# -------------------------------------------------------------------------- #

FALLBACK_KEYWORDS = [
    ("duplicate_charge", ("duplicado", "cobro doble", "charged twice", "dos veces", "twice", "two times", "merged")),
    ("unauthorized_charge", ("fraude", "unauthorized", "no autorizado", "did not make", "no la hice")),
    ("payment_not_received", ("never received", "nunca recib", "no llegó", "no recibio", "seller says")),
    ("app_issue", ("app", "balance", "saldo", "spinner", "carga")),
]


def fallback_classify(ticket_text: str, amount: float) -> dict:
    """Rule-based triage used when local inference is unavailable."""
    text = ticket_text.lower()
    category = "amount_discrepancy"          # default: money-vs-records mismatch
    severity = "medium"
    for candidate, keywords in FALLBACK_KEYWORDS:
        if any(k in text for k in keywords):
            category = candidate
            break
    if category == "unauthorized_charge":
        severity = "high"
    elif amount <= 0 or "app_issue" == category:
        severity = "low"
    refund = amount > 0 and category in ("duplicate_charge", "unauthorized_charge", "amount_discrepancy")
    return {
        "category": category,
        "severity": severity,
        "refund_request": refund,
        "amount_at_risk": round(float(amount), 2),
        "summary": "Deterministic keyword triage (LLM unavailable).",
        "suggested_resolution": (
            "Verify against the transaction ledger and refund if confirmed."
            if refund else
            "Verify with transaction log; no refund indicated by keywords."
        ),
        "confidence": 0.5,
    }
