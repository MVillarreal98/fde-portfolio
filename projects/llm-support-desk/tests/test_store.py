"""SQLite decision log and the SQL metrics built on it."""

import json
import sqlite3

import pytest
from fakes import FRAUD_4800, DeadLLM, FakeLLM, InjectionObeyingLLM, answer

from support_desk import Config, TriageService
from support_desk.store import DecisionStore

CFG = Config(db_path="")


@pytest.fixture
def store(tmp_path):
    return DecisionStore(str(tmp_path / "nested" / "decisions.db"))


def row(**overrides):
    base = {
        "ticket_ref": None, "ticket_sha256": "h", "ticket_text": "t", "ticket_amount": 10.0,
        "source": "llm", "model": "m", "prompt_version": "v", "prompt_sha256": "p",
        "proposed_category": "duplicate_charge", "proposed_severity": "medium",
        "category": "duplicate_charge", "severity": "medium", "confidence": 0.9,
        "refund_request": True, "exposure_mxn": 10.0, "action": "first_line_refund",
        "escalated": False, "rules_override": False, "rules_applied": [], "latency_ms": 100,
    }  # fmt: skip
    base.update(overrides)
    return base


def test_memory_path_is_rejected():
    with pytest.raises(ValueError):
        DecisionStore(":memory:")


def test_record_and_get_roundtrip(store):
    decision_id = store.record(row(rules_applied=["low_confidence"], escalated=True))
    saved = store.get(decision_id)
    assert saved["escalated"] == 1 and json.loads(saved["rules_applied"]) == ["low_confidence"]
    assert saved["created_at"].endswith("+00:00")
    assert store.get(decision_id + 1) is None


def test_metrics_sql(store):
    store.record(row())  # confident llm, first line
    store.record(
        row(
            category="app_issue", proposed_category="app_issue", escalated=True,
            rules_override=True, rules_applied=["fraud_signal", "exposure_above_cap"],
            action="escalate_to_human", latency_ms=300,
        )
    )  # fmt: skip
    for _ in range(2):
        store.record(
            row(
                source="fallback", model=None, escalated=True, rules_applied=["low_confidence"],
                action="escalate_to_human", latency_ms=0, confidence=0.5,
            )
        )  # fmt: skip
    store.record(row(proposed_category="chargeback", category="amount_discrepancy",
                     escalated=True, rules_override=True, rules_applied=["unknown_category"],
                     action="escalate_to_human"))  # fmt: skip

    m = store.metrics()
    assert m["totals"] == {
        "decisions": 5, "escalation_rate": 0.8, "rules_override_rate": 0.4, "fallback_rate": 0.4,
    }  # fmt: skip
    by_source = {r["source"]: r for r in m["by_source"]}
    assert by_source["llm"]["decisions"] == 3 and by_source["llm"]["avg_latency_ms"] == 166
    assert by_source["fallback"]["escalation_rate"] == 1.0
    assert m["by_action"][0] == {"action": "escalate_to_human", "decisions": 4}
    rules = {r["rule"]: r["decisions"] for r in m["rules_fired"]}
    assert rules == {
        "low_confidence": 2, "fraud_signal": 1, "exposure_above_cap": 1, "unknown_category": 1,
    }  # fmt: skip
    assert m["category_changed_by_rules"] == 1


def test_empty_store_metrics(store):
    m = store.metrics()
    assert m["totals"]["decisions"] == 0 and m["by_source"] == [] and m["rules_fired"] == []


def test_service_persists_every_decision_with_audit_fields(store):
    raw = answer()
    svc = TriageService(CFG, llm=FakeLLM(raw), store=store)
    out = svc.triage("I was charged twice for a $50 top-up", 50.0, ticket_ref="TK-1")
    saved = store.get(out["decision_id"])
    assert saved["ticket_ref"] == "TK-1" and saved["source"] == "llm"
    assert saved["model"] == CFG.model and saved["raw_output"] == raw
    assert saved["prompt_sha256"] == out["prompt_sha256"]
    assert saved["action"] == "first_line_refund" and saved["rules_override"] == 0
    assert len(saved["ticket_sha256"]) == 64

    fallback = TriageService(CFG, llm=DeadLLM(), store=store).triage("app crashed", 0.0)
    saved = store.get(fallback["decision_id"])
    assert saved["source"] == "fallback" and saved["model"] is None
    assert saved["raw_output"] is None and saved["fallback_note"].startswith("LLM unavailable")


def test_override_of_injected_answer_is_recorded(store):
    svc = TriageService(CFG, llm=InjectionObeyingLLM(), store=store)
    out = svc.triage(FRAUD_4800, 4800.0)
    saved = store.get(out["decision_id"])
    assert saved["proposed_severity"] == "low" and saved["severity"] == "high"
    assert saved["rules_override"] == 1 and saved["action"] == "escalate_to_human"


def test_persist_failure_still_returns_the_decision(caplog):
    class BrokenStore:
        def record(self, row):
            raise sqlite3.OperationalError("disk I/O error")

    out = TriageService(CFG, llm=FakeLLM(), store=BrokenStore()).triage("charged twice", 50.0)
    assert out["decision_id"] is None and out["source"] == "llm"
    assert "decision_persist_failed" in caplog.text
