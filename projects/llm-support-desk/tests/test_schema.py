"""The JSON contract between the model and the desk, plus the happy LLM path."""

import json

import pytest
from fakes import VALID_LLM_ANSWER, FakeLLM, answer

from support_desk import Config, TriageService
from support_desk.prompts import PROMPT_VERSION
from support_desk.schema import parse

CFG = Config(db_path="")


def test_valid_answer_parses_to_whitelisted_fields():
    out = parse(answer(escalated=False, source="human", refund_executed=True, action="close"))
    assert set(out) == {
        "category", "severity", "summary", "suggested_resolution", "confidence",
        "refund_request", "amount_at_risk",
    }  # fmt: skip


@pytest.mark.parametrize("raw", ["HIGH", "High", " high "])
def test_severity_is_stored_normalized(raw):
    assert parse(answer(severity=raw))["severity"] == "high"


def test_category_is_normalized():
    assert parse(answer(category="Duplicate Charge"))["category"] == "duplicate_charge"


@pytest.mark.parametrize(
    ("raw", "error"),
    [
        ("not json", "not valid JSON"),
        ("[1, 2]", "not a JSON object"),
        (json.dumps({"category": "app_issue"}), "missing field: severity"),
        (answer(confidence=True), "confidence has wrong type"),
        (answer(confidence="0.9"), "confidence has wrong type"),
        (answer(confidence=1.5), "confidence out of range"),
        (answer(severity="urgent"), "severity must be one of"),
        (answer(category="chargeback"), "unknown category"),
        (answer(amount_at_risk="abc"), "amount_at_risk is not numeric"),
        (answer(amount_at_risk=True), "amount_at_risk is not numeric"),
        (answer(amount_at_risk=-5000), "amount_at_risk must be a finite number >= 0"),
    ],
)
def test_contract_violations_are_rejected(raw, error):
    with pytest.raises(ValueError, match=error):
        parse(raw)


def test_nan_confidence_is_rejected():
    raw = VALID_LLM_ANSWER.replace('"confidence": 0.9', '"confidence": NaN')
    with pytest.raises(ValueError, match="confidence out of range"):
        parse(raw)


def test_coercions():
    out = parse(answer(refund_request="yes", amount_at_risk="120.456"))
    assert out["refund_request"] is True and out["amount_at_risk"] == 120.46
    raw = json.loads(VALID_LLM_ANSWER)
    del raw["refund_request"], raw["amount_at_risk"]
    out = parse(json.dumps(raw))
    assert out["refund_request"] is False and out["amount_at_risk"] == 0.0


def test_happy_path_llm_decision_is_first_line():
    llm = FakeLLM(VALID_LLM_ANSWER)
    out = TriageService(CFG, llm=llm).triage("I paid my $50 top-up twice", 50.0, "3 top-ups")
    assert out["source"] == "llm" and out["model"] == CFG.model
    assert out["category"] == "duplicate_charge" and out["action"] == "first_line_refund"
    assert out["escalated"] is False and out["rules_override"] is False
    assert out["prompt_version"] == PROMPT_VERSION and len(out["prompt_sha256"]) == 64
    assert out["decision_id"] is None  # no store configured
    assert len(llm.calls) == 1
