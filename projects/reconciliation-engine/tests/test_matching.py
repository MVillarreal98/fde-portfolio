"""Unit tests for the anomaly rules on a synthetic matched frame.

The fixtures go through the real `clean_ops` path so the tests cover the same
schema the production pipeline sees.
"""

import pandas as pd
import pytest

from reconciliation import Config
from reconciliation.anomalies import (
    rule_amount_mismatch,
    rule_duplicate_settlements,
    rule_orphans,
)
from reconciliation.cleaning import clean_ops
from reconciliation.matching import aggregate_billing, match_sources


def build():
    ops = pd.DataFrame({
        "transaction_id": ["T1", "T2", "T3"],
        "merchant": ["A", "B", "C"],
        "channel": ["OXXO", "SPEI", "CARD"],
        "amount": [100.00, 250.00, 75.00],            # T3: refund, fully settled
        "currency": ["MXN", "MXN", "MXN"],
        "status": ["captured", "captured", "refunded"],
        "recorded_at": ["2025-03-01 09:00", "2025-03-01 10:00", "2025-03-01 11:00"],
    })
    billing = pd.DataFrame({
        "statement_id": ["S1", "S2", "S3", "S4", "S5"],
        "transaction_ref": ["T1", "T1", "T2", "T3", "T4"],
        "settlement_amount": [100.00, 100.00, 249.50, 75.00, 120.00],
        "currency": ["MXN"] * 5,
        "settled_at": ["2025-03-02"] * 5,
        "processor_fee": [1.0, 1.0, 2.0, 3.0, 4.0],
    })
    cleaned = clean_ops(ops, Config())
    matched = match_sources(cleaned, aggregate_billing(billing))
    return matched, cleaned


@pytest.fixture()
def matched_and_ops():
    return build()


def test_duplicate_settlement_rule(matched_and_ops):
    matched, _ = matched_and_ops
    df = rule_duplicate_settlements(matched, Config())
    assert list(df["transaction_ref"]) == ["T1"]
    assert df.iloc[0]["settlement_count"] == 2


def test_amount_mismatch_rule(matched_and_ops):
    matched, _ = matched_and_ops
    df = rule_amount_mismatch(matched, Config())
    # T1 double-settles (+100.00 over the ops amount) and T2 under-settles
    # (-0.50): both are true amount disagreements.
    assert set(df["transaction_ref"]) == {"T1", "T2"}
    row = df[df["transaction_ref"] == "T2"].iloc[0]
    assert row["amount_difference"] == -0.50


def test_orphan_rules_exclude_refunds(matched_and_ops):
    matched, _ = matched_and_ops
    df = rule_orphans(matched, Config())
    # T3 is a refund that settled once: expected behavior, not an orphan.
    # T4 settled but was never recorded in the ops ledger: phantom revenue.
    refs = set(df["transaction_ref"])
    assert "T3" not in refs
    assert "T4" in refs
    row = df[df["transaction_ref"] == "T4"].iloc[0]
    assert "phantom" in row["discrepancy_type"]
