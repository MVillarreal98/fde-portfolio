"""Golden parity: the pandas engine and the DuckDB SQL engine must agree row for row.

Checked on the bundled demo data, on every edge case from the regression suite
and on seeded random datasets that mix every anomaly class at once.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from reconciliation import Config, run_reconciliation
from reconciliation.anomalies import RULE_COLUMNS
from reconciliation.matching import MATCHED_COLUMNS

from conftest import DATA, records, write_case

EDGE_CASES = {
    "blank_billing_ref": (
        "T1,A,OXXO,100.00,MXN,captured,2025-03-01 09:00\n",
        "S1,T1,100.00,MXN,2025-03-02,1\nS2,,500.00,MXN,2025-03-02,1\n",
    ),
    "thousands": (
        'T1,A,SPEI,"1,250.00",MXN,captured,2025-03-01 09:00\n',
        "S1,T1,1250.00,MXN,2025-03-02,1\n",
    ),
    "blank_ops_id": (
        ",A,SPEI,999.00,MXN,captured,2025-03-01 09:00\n",
        "S2,T2,10.00,MXN,2025-03-02,1\n",
    ),
    "status_case": (
        "T1,A,SPEI,450.00,MXN,Refunded,2025-03-01 09:00\n",
        "S9,T9,1.00,MXN,2025-03-02,1\n",
    ),
    "currency": (
        "T1,A,CARD,100.00,USD,captured,2025-03-01 09:00\n",
        "S1,T1,100.00,MXN,2025-03-02,1\n",
    ),
    "negative": (
        "T1,A,SPEI,-450.00,MXN,captured,2025-03-01 09:00\n"
        "T2,B,SPEI,-300.00,MXN,captured,2025-03-01 09:30\n",
        "S2,T2,300.00,MXN,2025-03-02,1\n",
    ),
    "zero_amount": (
        "T1,A,CARD,0.00,MXN,captured,2025-03-01 09:00\n",
        "S1,T1,5.00,MXN,2025-03-02,1\n",
    ),
    "dup_ops_id": (
        "T1,A,OXXO,100.00,MXN,captured,2025-03-01 09:00\n"
        "T1,B,OXXO,40.00,MXN,captured,2025-03-02 09:00\n",
        "S1,T1,100.00,MXN,2025-03-02,1\n",
    ),
    "cancelled_settled": (
        "T1,A,CARD,700.00,MXN,cancelled,2025-03-01 09:00\n",
        "S1,T1,700.00,MXN,2025-03-02,1\n",
    ),
    "numeric_ids": (
        "1001,A,OXXO,100.00,MXN,captured,2025-03-01 09:00\n",
        "S1,1001,100.00,MXN,2025-03-02,1\nS3,,5.00,MXN,2025-03-02,1\n",
    ),
    "split": (
        "T1,A,SPEI,100.00,MXN,captured,2025-03-01 09:00\n",
        "S1,T1,50.00,MXN,2025-03-02,1\nS2,T1,50.00,MXN,2025-03-03,1\n",
    ),
    "leading_zeros": (
        "00123,A,OXXO,100.00,MXN,captured,2025-03-01 09:00\n",
        "S1,123,100.00,MXN,2025-03-02,1\n",
    ),
    "cash_twins": (
        "T1,S,OXXO,100.00,MXN,captured,2025-03-01 09:00\n"
        "T2,S,OXXO,100.00,MXN,captured,2025-03-01 09:05\n",
        "S1,T1,100.00,MXN,2025-03-02,1\n",
    ),
    "empty_ops": ("", "S1,T1,100.00,MXN,2025-03-02,1\n"),
    "empty_both": ("", ""),
}


def _money(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}{abs(cents) // 100}.{abs(cents) % 100:02d}"


def random_case(seed: int, n: int = 400) -> tuple[str, str]:
    """Synthetic mix: retries, splits, partials, voids, currencies, duplicates, junk rows."""
    rng = np.random.default_rng(seed)
    ops_lines, billing_lines = [], []
    sid = 0
    for i in range(n):
        tid = f"T{i - 1:04d}" if i and rng.random() < 0.02 else f"T{i:04d}"  # duplicate IDs
        cents = int(rng.choice([5000, 7525, 10000, 120000])) * (-1 if rng.random() < 0.05 else 1)
        amount = f'"{cents // 100:,}.00"' if abs(cents) >= 100000 else _money(cents)
        if rng.random() < 0.01:
            amount = "n/a"
        status = rng.choice(
            ["captured", "Captured", "refunded", "CANCELLED", "void"],
            p=[0.82, 0.06, 0.04, 0.04, 0.04],
        )
        currency = "USD" if rng.random() < 0.03 else "MXN"
        minute = int(rng.integers(0, 240))
        merchant = f"Store {int(rng.integers(0, 6))}"
        channel = rng.choice(["OXXO", "SPEI", "CARD"])
        ops_lines.append(
            f"{tid},{merchant},{channel},{amount},{currency},{status},"
            f"2025-03-01 {8 + minute // 60:02d}:{minute % 60:02d}"
        )
        r = rng.random()
        parts: list[int] = []
        if r < 0.70:
            parts = [cents]
        elif r < 0.75:
            parts = [cents, cents]  # retry
        elif r < 0.80:
            parts = [cents // 2, cents - cents // 2]  # split
        elif r < 0.85:
            parts = [cents + int(rng.integers(-500, 500))]  # partial / over
        elif r < 0.88:
            parts = [cents, -cents]  # settled and reversed
        for p in parts:
            sid += 1
            cur = "USD" if rng.random() < 0.02 else "MXN"
            billing_lines.append(f"S{sid:05d},{tid},{_money(p)},{cur},2025-03-02,1")
    for j in range(8):  # phantom refs and junk billing rows
        sid += 1
        ref = "" if j % 4 == 0 else f"X{j:03d}"
        billing_lines.append(f"S{sid:05d},{ref},{_money(1000 + j)},MXN,2025-03-02,1")
    return "\n".join(ops_lines) + "\n", "\n".join(billing_lines) + "\n"


def run_both(ops: Path, billing: Path, out: Path, **kwargs: object):
    results = {}
    for engine in ("pandas", "sql"):
        cfg = Config(
            ops_path=ops, billing_path=billing, output_dir=out / engine, engine=engine, **kwargs
        )
        results[engine] = run_reconciliation(cfg)
    return results["pandas"], results["sql"]


def assert_same(pd_res, sql_res) -> None:
    assert list(pd_res.matched.columns) == MATCHED_COLUMNS
    assert list(sql_res.matched.columns) == MATCHED_COLUMNS
    assert records(pd_res.matched) == records(sql_res.matched)
    assert list(pd_res.findings) == list(sql_res.findings) == list(RULE_COLUMNS)
    for name, cols in RULE_COLUMNS.items():
        assert list(pd_res.findings[name].columns) == cols, name
        assert list(sql_res.findings[name].columns) == cols, name
        assert records(pd_res.findings[name]) == records(sql_res.findings[name]), name


def test_parity_on_demo_data(tmp_path: Path) -> None:
    pd_res, sql_res = run_both(
        DATA / "ops_transactions.csv", DATA / "billing_statements.csv", tmp_path
    )
    assert_same(pd_res, sql_res)
    assert len(pd_res.fired) == 6


@pytest.mark.parametrize("case", sorted(EDGE_CASES))
def test_parity_on_edge_cases(tmp_path: Path, case: str) -> None:
    ops, billing = write_case(tmp_path, *EDGE_CASES[case])
    assert_same(*run_both(ops, billing, tmp_path / "out"))


@pytest.mark.parametrize("seed", [1, 2, 3])
@pytest.mark.parametrize("window", [0, 10, 90])
def test_parity_on_random_mixes(tmp_path: Path, seed: int, window: int) -> None:
    ops, billing = write_case(tmp_path, *random_case(seed))
    pd_res, sql_res = run_both(ops, billing, tmp_path / "out", duplicate_window_minutes=window)
    assert_same(pd_res, sql_res)
    # The mix must actually exercise the rules, or parity would be vacuous.
    assert {
        "duplicate_settlements",
        "amount_mismatch",
        "orphans",
        "settled_but_cancelled",
        "currency_mismatch",
        "duplicate_ops_ids",
    } <= set(pd_res.fired)
    assert not pd_res.rejected.empty
