"""Regression tests for the 16 edge cases found in the v1.0.0 review.

Each case states the v1.0.0 behavior it guards against. All run on both engines.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from reconciliation import Config, run_reconciliation
from reconciliation.anomalies import LEAKAGE, PHANTOM, UNSETTLED_REFUND

from conftest import RunCase, write_case


def fired(res) -> dict[str, list[str]]:
    key = {"duplicate_ops_ids": "transaction_id", "duplicate_charge_candidates": "transaction_ids"}
    return {name: list(df[key.get(name, "transaction_ref")]) for name, df in res.fired.items()}


def test_01_blank_billing_ref_is_rejected_not_lost(run_case: RunCase) -> None:
    # v1.0.0: with pandas 3 the $500 settlement vanished from the report.
    res = run_case(
        "T1,A,OXXO,100.00,MXN,captured,2025-03-01 09:00\n",
        "S1,T1,100.00,MXN,2025-03-02,1\nS2,,500.00,MXN,2025-03-02,1\n",
    )
    assert fired(res) == {}
    assert res.rejected[["source", "statement_id", "reason"]].to_dict("records") == [
        {"source": "billing", "statement_id": "S2", "reason": "missing transaction_ref"}
    ]
    assert res.stats["billing"].amount_rejected_cents == 50000
    report = Path(res.report_path).read_text(encoding="utf-8")
    assert "## Rejected rows (1)" in report and "$500.00" in report
    assert res.needs_attention


def test_02_thousands_separator_is_parsed(run_case: RunCase) -> None:
    # v1.0.0: '1,250.00' was dropped silently and its settlement reported as phantom revenue.
    res = run_case(
        'T1,A,SPEI,"1,250.00",MXN,captured,2025-03-01 09:00\n'
        "T2,B,OXXO,10.00,MXN,captured,2025-03-01 10:00\n",
        "S1,T1,1250.00,MXN,2025-03-02,1\nS2,T2,10.00,MXN,2025-03-02,1\n",
    )
    assert fired(res) == {}
    assert res.rejected.empty


def test_03_blank_ops_id_is_rejected(run_case: RunCase) -> None:
    # v1.0.0: lost silently with pandas 2, orphan 'nan' with pandas 3.
    res = run_case(
        ",A,SPEI,999.00,MXN,captured,2025-03-01 09:00\n"
        "T2,B,OXXO,10.00,MXN,captured,2025-03-01 10:00\n",
        "S2,T2,10.00,MXN,2025-03-02,1\n",
    )
    assert fired(res) == {}
    assert res.rejected["reason"].tolist() == ["missing transaction_id"]
    assert res.stats["ops"].amount_rejected_cents == 99900


def test_04_status_casing_is_normalized(run_case: RunCase) -> None:
    # v1.0.0: 'Refunded' (capital R) was reported as revenue leakage.
    res = run_case(
        "T1,A,SPEI,450.00,MXN,Refunded,2025-03-01 09:00\n", "S9,T9,1.00,MXN,2025-03-02,1\n"
    )
    assert fired(res) == {"orphans": ["T9"]}


def test_05_currency_mismatch_is_reported(run_case: RunCase) -> None:
    # v1.0.0: USD 100 vs MXN 100 produced no finding.
    res = run_case(
        "T1,A,CARD,100.00,USD,captured,2025-03-01 09:00\n", "S1,T1,100.00,MXN,2025-03-02,1\n"
    )
    assert fired(res) == {"currency_mismatch": ["T1"]}


def test_06_negative_amounts_are_reconciled(run_case: RunCase) -> None:
    # v1.0.0: negative rows were invisible to every rule.
    res = run_case(
        "T1,A,SPEI,-450.00,MXN,captured,2025-03-01 09:00\n"
        "T2,B,SPEI,-300.00,MXN,captured,2025-03-01 09:30\n",
        "S2,T2,300.00,MXN,2025-03-02,1\n",
    )
    assert fired(res) == {"amount_mismatch": ["T2"], "orphans": ["T1"]}
    assert res.findings["orphans"]["discrepancy_type"].tolist() == [UNSETTLED_REFUND]
    assert res.findings["amount_mismatch"]["amount_difference_cents"].tolist() == [60000]


def test_07_zero_amount_ops_row_exists(run_case: RunCase) -> None:
    # v1.0.0: a recorded 0.00 charge was called 'settlement_without_ops_record'.
    res = run_case(
        "T1,A,CARD,0.00,MXN,captured,2025-03-01 09:00\n", "S1,T1,5.00,MXN,2025-03-02,1\n"
    )
    assert fired(res) == {"amount_mismatch": ["T1"]}


def test_08_duplicate_ops_id_is_its_own_finding(run_case: RunCase) -> None:
    # v1.0.0: settled total reported $200 when only $100 settled; no duplicate-ID finding.
    res = run_case(
        "T1,A,OXXO,100.00,MXN,captured,2025-03-01 09:00\n"
        "T1,B,OXXO,40.00,MXN,captured,2025-03-02 09:00\n",
        "S1,T1,100.00,MXN,2025-03-02,1\n",
    )
    assert fired(res) == {"amount_mismatch": ["T1"], "duplicate_ops_ids": ["T1"]}
    report = Path(res.report_path).read_text(encoding="utf-8")
    assert "**Settled total (billing):** $100.00" in report


def test_09_cancelled_but_settled(run_case: RunCase) -> None:
    # v1.0.0: no finding for a cancelled charge settled in full.
    res = run_case(
        "T1,A,CARD,700.00,MXN,cancelled,2025-03-01 09:00\n", "S1,T1,700.00,MXN,2025-03-02,1\n"
    )
    assert fired(res) == {"settled_but_cancelled": ["T1"]}


def test_10_numeric_ids_with_blank_ref(run_case: RunCase) -> None:
    # v1.0.0: '1001' vs '1001.0' made every transaction an orphan.
    res = run_case(
        "1001,A,OXXO,100.00,MXN,captured,2025-03-01 09:00\n"
        "1002,B,OXXO,50.00,MXN,captured,2025-03-01 10:00\n",
        "S1,1001,100.00,MXN,2025-03-02,1\nS2,1002,50.00,MXN,2025-03-02,1\n"
        "S3,,5.00,MXN,2025-03-02,1\n",
    )
    assert fired(res) == {}
    assert res.rejected["statement_id"].tolist() == ["S3"]
    assert sorted(res.matched["transaction_ref"]) == ["1001", "1002"]


def test_11_split_settlement_is_not_a_duplicate(run_case: RunCase) -> None:
    # v1.0.0: 50 + 50 for a 100 charge was flagged as duplicate settlement.
    res = run_case(
        "T1,A,SPEI,100.00,MXN,captured,2025-03-01 09:00\n",
        "S1,T1,50.00,MXN,2025-03-02,1\nS2,T1,50.00,MXN,2025-03-03,1\n",
    )
    assert fired(res) == {}


def test_12_negative_tolerance_is_refused(tmp_path: Path) -> None:
    # v1.0.0: accepted, and an exact match came out as a mismatch.
    with pytest.raises(ValueError, match="tolerance must be >= 0"):
        Config(ops_path=tmp_path / "o.csv", billing_path=tmp_path / "b.csv", amount_tolerance=-1)


def test_13_leading_zeros_are_significant(run_case: RunCase) -> None:
    # v1.0.0: '00123' and '123' were matched because both were read as the integer 123.
    res = run_case(
        "00123,A,OXXO,100.00,MXN,captured,2025-03-01 09:00\n", "S1,123,100.00,MXN,2025-03-02,1\n"
    )
    assert fired(res) == {"orphans": ["00123", "123"]}
    assert res.findings["orphans"]["discrepancy_type"].tolist() == [LEAKAGE, PHANTOM]


def test_14_identical_cash_payments_both_settled(run_case: RunCase) -> None:
    # v1.0.0: flagged as duplicate ops entries (154,095 false groups in a 1M-row benchmark).
    res = run_case(
        "T1,Convenience Store 01,OXXO,100.00,MXN,captured,2025-03-01 09:00\n"
        "T2,Convenience Store 01,OXXO,100.00,MXN,captured,2025-03-01 18:00\n",
        "S1,T1,100.00,MXN,2025-03-02,1\nS2,T2,100.00,MXN,2025-03-02,1\n",
    )
    assert fired(res) == {}


def test_15_empty_ops_file(run_case: RunCase) -> None:
    res = run_case("", "S1,T1,100.00,MXN,2025-03-02,1\n")
    assert fired(res) == {"orphans": ["T1"]}
    assert res.stats["ops"].rows_read == 0


def test_16_missing_column_fails_fast(tmp_path: Path, engine: str) -> None:
    ops, billing = write_case(tmp_path, "", "")
    ops.write_text("transaction_id,merchant,amount\nT1,A,1\n", encoding="utf-8")
    cfg = Config(ops_path=ops, billing_path=billing, output_dir=tmp_path / "out", engine=engine)
    with pytest.raises(ValueError, match="Missing expected columns"):
        run_reconciliation(cfg)
    assert not (tmp_path / "out").exists()
