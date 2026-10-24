"""One test (or more) per rule. Every test runs twice: pandas engine and SQL engine."""

from __future__ import annotations

from reconciliation.anomalies import LEAKAGE, PHANTOM, UNSETTLED_REFUND

from conftest import RunCase


def refs(df, col="transaction_ref"):
    return list(df[col])


def test_exact_match_produces_no_findings(run_case: RunCase) -> None:
    res = run_case(
        "T1,A,OXXO,100.00,MXN,captured,2025-03-01 09:00\n"
        "T2,B,SPEI,250.00,MXN,captured,2025-03-01 10:00\n",
        "S1,T1,100.00,MXN,2025-03-02,1\nS2,T2,250.00,MXN,2025-03-02,1\n",
    )
    assert res.fired == {}
    assert set(res.matched["recon_status"]) == {"matched"}
    assert not res.needs_attention


def test_duplicate_settlement_retry_is_flagged_once(run_case: RunCase) -> None:
    res = run_case(
        "T1,A,SPEI,3400.00,MXN,captured,2025-03-01 09:00\n",
        "S1,T1,3400.00,MXN,2025-03-02,1\nS2,T1,3400.00,MXN,2025-03-02,1\n",
    )
    dup = res.findings["duplicate_settlements"]
    assert dup.to_dict("records") == [
        {
            "transaction_ref": "T1",
            "merchant": "A",
            "channel": "SPEI",
            "ops_amount_cents": 340000,
            "settlement_total_cents": 680000,
            "amount_difference_cents": 340000,
            "settlement_count": 2,
            "statement_ids": "S1, S2",
        }
    ]
    # The same over-settlement is not counted again as an amount mismatch.
    assert res.findings["amount_mismatch"].empty


def test_split_settlement_that_adds_up_is_not_a_duplicate(run_case: RunCase) -> None:
    res = run_case(
        "T1,A,SPEI,100.00,MXN,captured,2025-03-01 09:00\n",
        "S1,T1,50.00,MXN,2025-03-02,1\nS2,T1,50.00,MXN,2025-03-03,1\n",
    )
    assert res.fired == {}


def test_partial_settlement_with_distinct_amounts_is_a_mismatch(run_case: RunCase) -> None:
    res = run_case(
        "T1,A,SPEI,100.00,MXN,captured,2025-03-01 09:00\n",
        "S1,T1,60.00,MXN,2025-03-02,1\nS2,T1,30.00,MXN,2025-03-03,1\n",
    )
    assert refs(res.findings["amount_mismatch"]) == ["T1"]
    assert res.findings["duplicate_settlements"].empty


def test_amount_mismatch_sorted_and_tolerance_inclusive(run_case: RunCase) -> None:
    res = run_case(
        "T1,A,OXXO,100.00,MXN,captured,2025-03-01 09:00\n"
        "T2,B,OXXO,100.00,MXN,captured,2025-03-01 09:00\n"
        "T3,C,OXXO,100.00,MXN,captured,2025-03-01 09:00\n"
        "T4,D,OXXO,100.00,MXN,captured,2025-03-01 09:00\n",
        "S1,T1,100.01,MXN,2025-03-02,1\n"  # exactly at tolerance: noise
        "S2,T2,99.98,MXN,2025-03-02,1\n"  # 0.02 under
        "S3,T3,150.00,MXN,2025-03-02,1\n"  # 50 over
        "S4,T4,99.50,MXN,2025-03-02,1\n",  # 0.50 under
    )
    mismatch = res.findings["amount_mismatch"]
    assert refs(mismatch) == ["T3", "T4", "T2"]
    assert list(mismatch["amount_difference_cents"]) == [5000, -50, -2]


def test_zero_tolerance_flags_one_cent(run_case: RunCase) -> None:
    res = run_case(
        "T1,A,OXXO,100.00,MXN,captured,2025-03-01 09:00\n",
        "S1,T1,100.01,MXN,2025-03-02,1\n",
        amount_tolerance="0",
    )
    assert refs(res.findings["amount_mismatch"]) == ["T1"]


def test_currency_mismatch(run_case: RunCase) -> None:
    res = run_case(
        "T1,A,CARD,100.00,usd,captured,2025-03-01 09:00\n"
        "T2,B,CARD,100.00,MXN,captured,2025-03-01 09:00\n",
        "S1,T1,100.00,MXN,2025-03-02,1\n"
        "S2,T2,60.00,MXN,2025-03-02,1\nS3,T2,40.00,USD,2025-03-02,1\n",
    )
    cur = res.findings["currency_mismatch"]
    assert cur[["transaction_ref", "ops_currency", "settlement_currency"]].to_dict("records") == [
        {"transaction_ref": "T1", "ops_currency": "USD", "settlement_currency": "MXN"},
        {"transaction_ref": "T2", "ops_currency": "MXN", "settlement_currency": "MXN/USD"},
    ]
    assert res.findings["amount_mismatch"].empty


def test_settled_but_cancelled_any_casing(run_case: RunCase) -> None:
    res = run_case(
        "T1,A,CARD,700.00,MXN,Cancelled,2025-03-01 09:00\n"
        "T2,B,CARD,450.00,MXN,REFUNDED,2025-03-01 09:00\n"
        "T3,C,CARD,300.00,MXN,void,2025-03-01 09:00\n",
        "S1,T1,700.00,MXN,2025-03-02,1\n"
        "S2,T2,450.00,MXN,2025-03-02,1\n"
        "S3,T3,300.00,MXN,2025-03-02,1\nS4,T3,-300.00,MXN,2025-03-03,1\n",  # reversed: nets 0
    )
    sbc = res.findings["settled_but_cancelled"]
    assert refs(sbc) == ["T1", "T2"]
    assert list(sbc["status"]) == ["cancelled", "refunded"]
    assert res.matched.set_index("transaction_ref").loc["T3", "recon_status"] == "matched"


def test_orphans_both_directions_and_refunds(run_case: RunCase) -> None:
    res = run_case(
        "T1,A,SPEI,1250.00,MXN,captured,2025-03-01 09:00\n"
        "T2,B,SPEI,-450.00,MXN,captured,2025-03-01 09:00\n"
        "T3,C,SPEI,80.00,MXN,cancelled,2025-03-01 09:00\n",  # reversed, never settled: expected
        "S9,T9,250.00,MXN,2025-03-02,1\n",
    )
    orphans = res.findings["orphans"]
    assert orphans[["transaction_ref", "discrepancy_type"]].to_dict("records") == [
        {"transaction_ref": "T1", "discrepancy_type": LEAKAGE},
        {"transaction_ref": "T2", "discrepancy_type": UNSETTLED_REFUND},
        {"transaction_ref": "T9", "discrepancy_type": PHANTOM},
    ]
    status = res.matched.set_index("transaction_ref")["recon_status"]
    assert status["T3"] == "cancelled_not_settled"


def test_negative_amount_settled_with_wrong_sign_is_a_mismatch(run_case: RunCase) -> None:
    res = run_case(
        "T1,A,SPEI,-300.00,MXN,captured,2025-03-01 09:00\n",
        "S1,T1,300.00,MXN,2025-03-02,1\n",
    )
    assert res.findings["amount_mismatch"]["amount_difference_cents"].tolist() == [60000]


def test_duplicate_ops_ids_do_not_inflate_totals(run_case: RunCase) -> None:
    res = run_case(
        "T1,A,OXXO,100.00,MXN,captured,2025-03-01 09:00\n"
        "T1,B,OXXO,40.00,MXN,captured,2025-03-02 09:00\n",
        "S1,T1,100.00,MXN,2025-03-02,1\n",
    )
    assert res.findings["duplicate_ops_ids"].to_dict("records") == [
        {
            "transaction_id": "T1",
            "occurrences": 2,
            "ops_amount_total_cents": 14000,
            "row_numbers": "1, 2",
        }
    ]
    assert int(res.matched["settlement_total_cents"].sum()) == 10000  # was 200.00 before
    assert int(res.matched["ops_amount_cents"].sum()) == 14000
    assert refs(res.findings["amount_mismatch"]) == ["T1"]


DUP_OPS = (
    "T1,Store 1,OXXO,75.00,MXN,captured,2025-03-01 17:45\n"
    "T2,Store 1,OXXO,75.00,MXN,captured,2025-03-01 17:52\n"  # 7 min later, never settled
    "T3,Store 1,OXXO,75.00,MXN,captured,2025-03-01 18:30\n"  # 38 min later: own group
    "T4,Store 1,CARD,75.00,MXN,captured,2025-03-01 17:46\n"  # other channel
    "T5,Store 1,OXXO,80.00,MXN,captured,2025-03-01 17:46\n"  # other amount
    "T6,Store 1,OXXO,75.00,MXN,captured,not a date\n"  # no time: out of the heuristic
)
DUP_BILLING = "S1,T1,75.00,MXN,2025-03-02,1\nS3,T3,75.00,MXN,2025-03-02,1\n"


def test_duplicate_charge_candidates_need_window_and_missing_settlement(run_case: RunCase) -> None:
    res = run_case(DUP_OPS, DUP_BILLING)
    cand = res.findings["duplicate_charge_candidates"]
    assert len(cand) == 1
    row = cand.iloc[0]
    assert (row["merchant"], row["channel"], int(row["amount_cents"])) == ("Store 1", "OXXO", 7500)
    assert (int(row["occurrences"]), int(row["settled_count"])) == (2, 1)
    assert row["transaction_ids"] == "T1, T2"


def test_duplicate_charge_window_is_configurable(run_case: RunCase) -> None:
    # A 60-minute window chains T1 -> T2 -> T3 into one group of three.
    res = run_case(DUP_OPS, DUP_BILLING, duplicate_window_minutes=60)
    cand = res.findings["duplicate_charge_candidates"]
    assert cand["transaction_ids"].tolist() == ["T1, T2, T3"]
    # A 5-minute window separates them: nothing left to flag.
    res = run_case(DUP_OPS, DUP_BILLING, duplicate_window_minutes=5)
    assert res.findings["duplicate_charge_candidates"].empty


def test_identical_payments_that_both_settled_are_not_duplicates(run_case: RunCase) -> None:
    res = run_case(
        "T1,Store 1,OXXO,100.00,MXN,captured,2025-03-01 09:00\n"
        "T2,Store 1,OXXO,100.00,MXN,captured,2025-03-01 09:00\n",
        "S1,T1,100.00,MXN,2025-03-02,1\nS2,T2,100.00,MXN,2025-03-02,1\n",
    )
    assert res.findings["duplicate_charge_candidates"].empty
    assert res.fired == {}


def test_each_rule_has_a_csv_even_when_empty(run_case: RunCase) -> None:
    res = run_case(
        "T1,A,OXXO,1.00,MXN,captured,2025-03-01 09:00\n", "S1,T1,1.00,MXN,2025-03-02,1\n"
    )
    names = sorted(p.rsplit("anomalies_", 1)[1] for p in res.csv_paths)
    assert names == sorted(f"{n}.csv" for n in res.findings)
    assert len(names) == 7
