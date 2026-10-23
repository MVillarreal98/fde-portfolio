"""Rules-layer tests and LLM-independent service behavior.

The LLM is fakeable by construction: `TriageService` accepts any object with a
`.chat(messages) -> str` method, so business behavior is tested deterministically
without local inference.
"""

from support_desk import Config, TriageService
from support_desk.rules import post_validate, fallback_classify

CFG = Config()


class FakeLLM:
    def __init__(self, raw: str):
        self._raw = raw

    def chat(self, messages):
        return self._raw


VALID_LLM_ANSWER = (
    '{"category": "unauthorized_charge", "severity": "low", "refund_request": true,'
    ' "amount_at_risk": 349.0, "summary": "Customer denies the charge.",'
    ' "suggested_resolution": "Block card and refund.", "confidence": 0.9}'
)


def test_fallback_when_llm_down():
    class DeadLLM:
        def chat(self, messages):
            raise RuntimeError("connection refused")

    svc = TriageService(CFG, llm=Faulted(DeadLLM()))
    out = svc.triage("I was charged twice for the same top-up at OXXO", 50.0)
    assert out["source"] == "fallback"
    assert out["category"] == "duplicate_charge"


class Faulted:
    """Wraps any client and re-raises everything as LLMUnavailable-equivalent."""

    def __init__(self, inner):
        self._inner = inner

    def chat(self, messages):
        from support_desk.llm_client import LLMUnavailable
        try:
            return self._inner.chat(messages)
        except Exception as exc:
            raise LLMUnavailable(str(exc))


def test_rules_enforce_unauthorized_override_and_refund_cap():
    d = {"category": "unauthorized_charge", "severity": "low", "refund_request": True,
         "summary": "x", "suggested_resolution": "refund now", "confidence": 0.9}
    out = post_validate(d, ticket_amount=1200.00, cfg=CFG)
    # unauthorized charges are never low-severity
    assert out["severity"] == "high" and out["escalated"]
    # refund above the 500 cap is escalated to supervisor
    assert "supervisor" in out["suggested_resolution"].lower()


MODEL_UPGRADE_OUTPUT = (
    '{"category": "duplicate", "severity": "high", "summary": "s",'
    ' "suggested_resolution": "r", "confidence": 0.9}'
)


def test_schema_contract_rejects_unknown_category():
    svc = TriageService(CFG, llm=Faulted(FakeLLM(MODEL_UPGRADE_OUTPUT)))
    out = svc.triage("They charged me two times", 80.0)
    assert out["source"] == "fallback"
    assert "Invalid model output" in (out.get("fallback_note") or "")


def test_low_confidence_always_escalates():
    d = {"category": "app_issue", "severity": "low", "refund_request": False,
         "summary": "s", "suggested_resolution": "r", "confidence": 0.2}
    out = post_validate(d, ticket_amount=0.0, cfg=CFG)
    assert out["escalated"]
    assert "human review" in out["suggested_resolution"].lower()
