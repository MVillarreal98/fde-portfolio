"""Unit tests for the anomaly rules over the matched frame."""

import pandas as pd
import pytest

from reconciliation import Config
from reconciliation.matching import aggregate_billing, match_sources
from reconciliation.anomalies import (
    rule_amount_mismatch,
    rule_duplicate_settlements,
    rule_orphans,
)


def build():
    ops = pd.DataFrame({
        "transaction_ref": ["T1", "T2", "T3", "T4"],
        "merchant": ["A", "B", "C", "D"],
        "channel": ["OXXO", "SPEI", "CARD", "OXXO"],
        "ops_amount": [100.00, 250.00, 75.00, 0.0],   # T4: orphan billing case
        "currency": ["MXN", "MXN", "MXN", "MXN"],
        "status": ["captured", "captured", "refunded", "captured"],
        "recorded_date": [pd.Timestamp("2025-03-01").date()] * 4,
    })
    billing = pd.DataFrame({
        "statement_id": ["S1", "S2", "S3", "S4a", "S4b", "S5"],
        "transaction_ref": ["T1", "T1", "T2", "T3", "T3", "T4"],
        "settlement_amount": [100.00, 100.00, 249.50, 75.00, 75.00, 0.0],
        "currency": ["MXN"] * 6,
    })
    matched = match_sources(ops, aggregate_billing(billing))
    return matched, ops


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
    assert list(df["transaction_ref"]) == ["T2"]     # 249.50 vs 250.00
    assert df.iloc[0]["amount_difference"] == -0.50


def test_orphan_rules_exclude_refunds(matched_and_ops):
    matched, _ = matched_and_ops
    df = rule_orphans(matched, Config())
    # T3 is refunded and never settle-flagged; T4 settled but never recorded.
    refs = set(df["transaction_ref"])
    assert "T3" not in refs
    assert "T4" in refs
    row = df[df["transaction_ref"] == "T4"].iloc[0]
    assert "phantom" in row["discrepancy_type"]
