"""Rules-layer tests and LLM-independent service behavior."""

import pytest
from fakes import DeadLLM, FakeLLM, answer

from support_desk import Config, TriageService
from support_desk.rules import (
    ESCALATE,
    FIRST_LINE_REFUND,
    FIRST_LINE_REVIEW,
    fallback_classify,
    post_validate,
)

CFG = Config(db_path="")


def proposal(**overrides) -> dict:
    base = {
        "category": "duplicate_charge",
        "severity": "medium",
        "refund_request": True,
        "amount_at_risk": 50.0,
        "summary": "s",
        "suggested_resolution": "refund now",
        "confidence": 0.9,
    }
    base.update(overrides)
    return base


def test_fallback_when_llm_down():
    svc = TriageService(CFG, llm=DeadLLM())
    out = svc.triage("I was charged twice for the same top-up at OXXO", 50.0)
    assert out["source"] == "fallback"
    assert out["category"] == "duplicate_charge"
    assert out["fallback_note"].startswith("LLM unavailable")
    assert out["escalated"] and "low_confidence" in out["rules_applied"]


def test_unexpected_client_error_degrades_to_fallback():
    class Boom:
        def chat(self, messages):
            raise AttributeError("'list' object has no attribute 'get'")

    out = TriageService(CFG, llm=Boom()).triage("I was charged twice", 80.0)
    assert out["source"] == "fallback"
    assert out["fallback_note"] == "LLM client error: AttributeError"


def test_rules_enforce_unauthorized_override_and_refund_cap():
    d = proposal(category="unauthorized_charge", severity="low")
    out = post_validate(d, ticket_amount=1200.00, cfg=CFG)
    # unauthorized charges are never low-severity
    assert out["severity"] == "high" and out["escalated"]
    # money above the 500 cap is escalated to supervisor
    assert {"unauthorized_charge", "exposure_above_cap"} <= set(out["rules_applied"])
    assert out["suggested_resolution"] == (
        "Escalate to supervisor (money at stake above the first-line cap (500.00 MXN); "
        "unauthorized charges always go to a human). Proposed: refund now"
    )
    assert out["action"] == ESCALATE


def test_schema_contract_rejects_unknown_category():
    svc = TriageService(CFG, llm=FakeLLM(answer(category="duplicate")))
    out = svc.triage("They charged me two times", 80.0)
    assert out["source"] == "fallback"
    assert "Invalid model output" in out["fallback_note"]


def test_low_confidence_always_escalates():
    d = proposal(category="app_issue", severity="low", refund_request=False, confidence=0.2)
    out = post_validate(d, ticket_amount=0.0, cfg=CFG)
    assert out["escalated"] and out["rules_applied"] == ["low_confidence"]
    # the model itself was unsure: escalating is not an override of its proposal
    assert out["rules_override"] is False


@pytest.mark.parametrize("severity", ["LOW", "Low", " low ", "low"])
def test_unauthorized_severity_rule_is_case_insensitive(severity):
    out = post_validate(proposal(category="unauthorized_charge", severity=severity), 100.0, CFG)
    assert out["severity"] == "high"
    assert out["escalated"] and out["action"] == ESCALATE


def test_unauthorized_always_escalates_even_when_model_is_confident_and_high():
    out = post_validate(proposal(category="unauthorized_charge", severity="high"), 100.0, CFG)
    assert out["escalated"] and "unauthorized_charge" in out["rules_applied"]


def test_unknown_severity_fails_closed():
    out = post_validate(proposal(severity="urgent"), 50.0, CFG)
    assert out["severity"] == "high" and out["escalated"]
    assert "unknown_severity" in out["rules_applied"]


def test_unknown_category_is_replaced_and_escalated():
    out = post_validate(proposal(category="chargeback"), 50.0, CFG)
    assert out["category"] == "amount_discrepancy"
    assert out["confidence"] <= 0.4 and out["escalated"] and out["rules_override"]


def test_refund_cap_uses_model_amount_when_it_is_larger():
    # The ticket says 100 but the model proposes refunding 25,000: above the cap.
    out = post_validate(proposal(amount_at_risk=25000.0), ticket_amount=100.0, cfg=CFG)
    assert out["exposure_mxn"] == 25000.0
    assert out["escalated"] and "exposure_above_cap" in out["rules_applied"]
    assert out["action"] == ESCALATE and out["rules_override"]


def test_refund_cap_uses_ticket_amount_when_model_lowers_it():
    out = post_validate(proposal(amount_at_risk=0.0), ticket_amount=1200.0, cfg=CFG)
    assert out["exposure_mxn"] == 1200.0 and out["escalated"]


def test_cap_is_configurable():
    cfg = Config(db_path="", refund_cap_mxn=1000.0)
    assert not post_validate(proposal(), 800.0, cfg)["escalated"]
    assert post_validate(proposal(), 1000.01, cfg)["escalated"]


def test_refund_within_cap_is_first_line():
    out = post_validate(proposal(), ticket_amount=50.0, cfg=CFG)
    assert out["action"] == FIRST_LINE_REFUND
    assert not out["escalated"] and out["rules_applied"] == []
    assert out["rules_override"] is False
    assert out["suggested_resolution"] == "refund now"


def test_no_refund_within_cap_is_first_line_review():
    d = proposal(category="amount_discrepancy", refund_request=False)
    assert post_validate(d, 30.0, CFG)["action"] == FIRST_LINE_REVIEW


def test_money_on_app_issue_escalates():
    d = proposal(category="app_issue", severity="low", refund_request=False, amount_at_risk=0)
    out = post_validate(d, ticket_amount=120.0, cfg=CFG)
    assert out["escalated"] and out["rules_applied"] == ["money_on_app_issue"]


def test_fraud_language_in_ticket_escalates_whatever_the_proposal():
    d = proposal(category="app_issue", severity="low", refund_request=False, amount_at_risk=0)
    out = post_validate(d, 0.0, CFG, ticket_text="No reconozco este cargo")
    assert out["severity"] == "high" and out["escalated"]
    assert out["rules_applied"] == ["fraud_signal"] and out["rules_override"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("My money disappeared from my account", "amount_discrepancy"),  # 'app' inside a word
        ("Hice una recarga de 200 y me cobraron 250", "amount_discrepancy"),  # 'carga' in 'recarga'
        ("No reconozco este cargo de 2,000 pesos", "unauthorized_charge"),
        ("Me hicieron un cargo no autorizado dos veces", "unauthorized_charge"),  # fraud first
        ("Alguien usó mi tarjeta sin permiso", "unauthorized_charge"),
        ("I did not authorize this purchase", "unauthorized_charge"),
        ("Mi transferencia SPEI no llego al destinatario", "payment_not_received"),
        ("La app no carga mi saldo", "app_issue"),
        ("I paid twice for one top-up", "duplicate_charge"),
    ],
)
def test_fallback_lexicon(text, expected):
    assert fallback_classify(text, 100.0)["category"] == expected


def test_fallback_refund_policy():
    assert fallback_classify("the seller never received it", 1200.0)["refund_request"] is True
    assert fallback_classify("the app shows a spinner", 50.0)["refund_request"] is False
    assert fallback_classify("charged twice", 0.0)["refund_request"] is False


@pytest.mark.parametrize("amount", [-5000.0, float("nan"), float("inf"), "mil pesos"])
def test_service_rejects_invalid_amounts(amount):
    out = TriageService(CFG, llm=FakeLLM()).triage("charged twice", amount)
    assert out["source"] == "input" and "amount" in out["error"]


def test_service_rejects_empty_text():
    assert TriageService(CFG, llm=FakeLLM()).triage("   ", 10.0)["error"] == "empty ticket text"
