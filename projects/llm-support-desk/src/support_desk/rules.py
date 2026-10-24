"""Deterministic business-rules layer.

The model may propose; the rules dispose. Two kinds of checks run here, and both
can only ADD an escalation or RAISE severity — nothing the model returns can
lower them:

- Ticket guardrails, computed from the customer text and the operator-entered
  amount alone (never from model output): fraud/chargeback language and money
  above the first-line cap always go to a human. A prompt injection that fools
  the model cannot switch these off.
- Policy checks on the proposal: category whitelist, severity normalization,
  unauthorized-charge override, cap on max(ticket amount, model amount), money
  on an "app_issue" claim, and the confidence threshold.

The final `action` is computed here; the model's free text is advisory only.
"""

from __future__ import annotations

import re

from .config import REFUND_AUTOCAP_MXN, TRIAGE_CATEGORIES, Config

__all__ = [
    "ESCALATE",
    "FIRST_LINE_REFUND",
    "FIRST_LINE_REVIEW",
    "FRAUD_SIGNALS",
    "REFUND_AUTOCAP_MXN",
    "fallback_classify",
    "post_validate",
    "ticket_guardrails",
]

# The only actions the desk can take. Rules pick one; the model never does.
ESCALATE = "escalate_to_human"
FIRST_LINE_REFUND = "first_line_refund"
FIRST_LINE_REVIEW = "first_line_review"

VALID_SEVERITY = ("low", "medium", "high")

# Fraud / chargeback language, English + Spanish (accents optional). Word-bounded
# matching, so "recarga" never matches "carga" and "disappeared" never matches "app".
FRAUD_SIGNALS = re.compile(
    r"\b("
    r"fraud\w*|fraude|chargeback|contracargo\w*|"
    r"unauthori[sz]ed|not authori[sz]ed|did ?n[o'’]t authori[sz]e|"
    r"no autoric[eé]|no autorizad[oa]s?|sin (mi )?(permiso|autorizaci[oó]n)|"
    r"did ?n[o'’]t make|never made|"
    r"no (la|lo) hice|yo no (la |lo )?hice|no hice (esa|ese|este|esta)|"
    r"no reconozco|desconozco|do ?n[o'’]t recogni[sz]e|not recogni[sz]ed|"
    r"stolen|robad[oa]|me robaron|hacked|hacke[oó]|hackearon|clonad[oa]|cloned|"
    r"someone (else )?used my|alguien us[oó]|identity theft|suplantaci[oó]n"
    r")\b",
    re.IGNORECASE,
)

# Human-readable reason for every rule id that can appear in `rules_applied`.
RULE_NOTES = {
    "unknown_category": "category outside the taxonomy",
    "unknown_severity": "severity outside low/medium/high",
    "fraud_signal": "fraud/chargeback language in the customer text",
    "unauthorized_charge": "unauthorized charges always go to a human",
    "exposure_above_cap": "money at stake above the first-line cap",
    "money_on_app_issue": "money at stake on a claim classified as app issue",
    "low_confidence": "confidence at or below the escalation threshold",
}


def ticket_guardrails(ticket_text: str, ticket_amount: float, cfg: Config) -> list[str]:
    """Escalation reasons derived from the ticket alone — never from model output."""
    reasons = []
    if FRAUD_SIGNALS.search(ticket_text or ""):
        reasons.append("fraud_signal")
    if ticket_amount > cfg.refund_cap_mxn:
        reasons.append("exposure_above_cap")
    return reasons


def post_validate(decision: dict, ticket_amount: float, cfg: Config, ticket_text: str = "") -> dict:
    """Enforce policy invariants on a (validated) model or fallback proposal."""
    d = dict(decision)
    applied: list[str] = []

    def fire(rule: str) -> None:
        if rule not in applied:
            applied.append(rule)

    proposed_category = d.get("category")
    proposed_confidence = float(d.get("confidence", 0.0))
    if proposed_category not in TRIAGE_CATEGORIES:  # defense in depth
        d["category"] = "amount_discrepancy"
        d["confidence"] = min(proposed_confidence, 0.4)
        fire("unknown_category")

    # Normalized here too, so 'LOW' / 'Low' can never skip a severity rule.
    proposed_severity = str(d.get("severity", "")).strip().lower()
    severity = proposed_severity
    if severity not in VALID_SEVERITY:
        severity = "high"  # fail closed
        fire("unknown_severity")

    # The model can raise the money at stake, never lower it below the operator's amount.
    exposure = max(float(ticket_amount), float(d.get("amount_at_risk") or 0.0))
    d["exposure_mxn"] = round(exposure, 2)

    # 1) Ticket guardrails: independent of anything the model said.
    for rule in ticket_guardrails(ticket_text, ticket_amount, cfg):
        fire(rule)
    if "fraud_signal" in applied:
        severity = "high"

    # 2) Checks on the proposal.
    if d["category"] == "unauthorized_charge":
        severity = "high"
        fire("unauthorized_charge")
    if exposure > cfg.refund_cap_mxn:
        fire("exposure_above_cap")
    if d["category"] == "app_issue" and ticket_amount > 0:
        fire("money_on_app_issue")
    if float(d["confidence"]) <= cfg.escalation_threshold:
        fire("low_confidence")

    d["severity"] = severity
    escalated = bool(applied)  # every rule above routes the ticket to a human
    if escalated:
        cap_note = f" ({cfg.refund_cap_mxn:.2f} MXN)"
        notes = "; ".join(
            RULE_NOTES[r] + (cap_note if r == "exposure_above_cap" else "") for r in applied
        )
        d["suggested_resolution"] = (
            f"Escalate to supervisor ({notes}). Proposed: {d.get('suggested_resolution', '')}"
        )
        action = ESCALATE
    elif d.get("refund_request") and exposure > 0:
        action = FIRST_LINE_REFUND
    else:
        action = FIRST_LINE_REVIEW

    d["escalated"] = escalated
    d["action"] = action
    d["rules_applied"] = applied
    # Override = the rules changed what the proposal said, or escalated a proposal
    # that came in confident (above the threshold): "the model was sure, policy said no".
    d["rules_override"] = (
        d["category"] != proposed_category
        or severity != proposed_severity
        or (escalated and proposed_confidence > cfg.escalation_threshold)
    )
    return d


# -------------------------------------------------------------------------- #
# Deterministic fallback classifier: keyword-driven, auditable by hand.      #
# -------------------------------------------------------------------------- #

# Order matters: fraud first, so "cargo no autorizado dos veces" is not downgraded
# to a duplicate charge.
FALLBACK_KEYWORDS = [
    ("unauthorized_charge", FRAUD_SIGNALS),
    (
        "duplicate_charge",
        re.compile(
            r"\b(duplicad[oa]s?|cobro doble|doble cobro|cobraron doble|dos veces|"
            r"charged twice|twice|two times|double[- ]charged)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "payment_not_received",
        re.compile(
            r"\b(never received|not received|did ?n[o'’]t receive|never arrived|"
            r"did ?n[o'’]t arrive|has ?n[o'’]t arrived|"
            r"nunca (me |le |lo |la )?(lleg[oó]|recib\w*)|"
            r"no (me |le )?(ha )?(lleg[oó]|llegado|recibi[oó]|recibido))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "app_issue",
        re.compile(
            r"\b(app|aplicaci[oó]n|balance|saldo|spinner|no carga|se cierra|crash\w*|"
            r"login|iniciar sesi[oó]n)\b",
            re.IGNORECASE,
        ),
    ),
]


def fallback_classify(ticket_text: str, amount: float) -> dict:
    """Rule-based triage used when local inference is unavailable."""
    category = "amount_discrepancy"  # default: money-vs-records mismatch
    for candidate, pattern in FALLBACK_KEYWORDS:
        if pattern.search(ticket_text):
            category = candidate
            break
    severity = "medium"
    if category == "unauthorized_charge":
        severity = "high"
    elif amount <= 0 or category == "app_issue":
        severity = "low"
    refund_eligible_categories = (
        "duplicate_charge",
        "payment_not_received",
        "unauthorized_charge",
        "amount_discrepancy",
    )
    refund = amount > 0 and category in refund_eligible_categories
    return {
        "category": category,
        "severity": severity,
        "refund_request": refund,
        "amount_at_risk": round(float(amount), 2),
        "summary": "Deterministic keyword triage (LLM unavailable).",
        "suggested_resolution": (
            "Verify against the transaction ledger and refund if confirmed."
            if refund
            else "Verify with transaction log; no refund indicated by keywords."
        ),
        # Below the default escalation threshold (0.60): fallback output goes to a human.
        "confidence": 0.5,
    }
