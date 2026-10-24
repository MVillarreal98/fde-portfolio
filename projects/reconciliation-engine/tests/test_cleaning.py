"""Ingestion and cleaning: identifiers stay text, money becomes exact cents, bad rows are kept."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from reconciliation import Config
from reconciliation.cleaning import clean_billing, clean_ops, parse_amount_cents
from reconciliation.loaders import load_billing, load_ops

from conftest import write_case


@pytest.mark.parametrize(
    ("raw", "cents"),
    [
        ("1250", 125000),
        ("1250.5", 125050),
        ("1,250.00", 125000),
        ("1,234,567.89", 123456789),
        (" 48.50 ", 4850),
        ("-300.00", -30000),
        ("+12.30", 1230),
        ("10.500", 1050),
        ("0", 0),
        ("0.07", 7),
        ("007.00", 700),
    ],
)
def test_parse_amount_valid(raw: str, cents: int) -> None:
    parsed, reason = parse_amount_cents(pd.Series([raw]))
    assert parsed.iloc[0] == cents
    assert reason.iloc[0] == ""


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ("", "missing amount"),
        ("   ", "missing amount"),
        ("abc", "unparseable amount"),
        ("1.250,00", "unparseable amount"),
        ("12,50", "unparseable amount"),
        ("$100.00", "unparseable amount"),
        ("1e3", "unparseable amount"),
        ("10.505", "amount has sub-cent digits"),
        ("12345678901234", "amount out of range"),
    ],
)
def test_parse_amount_invalid_is_explained(raw: str, reason: str) -> None:
    parsed, why = parse_amount_cents(pd.Series([raw]))
    assert parsed.isna().iloc[0]
    assert why.iloc[0] == reason


def test_parse_amount_never_uses_float() -> None:
    # 0.1 + 0.2 style drift cannot happen: every value is an exact integer of cents.
    parsed, _ = parse_amount_cents(pd.Series(["0.10", "0.20", "1,000,000.01"]))
    assert parsed.sum() == 10 + 20 + 100000001
    assert str(parsed.dtype) == "Int64"


def test_ids_are_read_as_text(tmp_path: Path) -> None:
    ops, billing = write_case(
        tmp_path,
        "00123,A,OXXO,1.00,MXN,captured,2025-03-01 09:00\n"
        "1001,B,OXXO,2.00,MXN,captured,2025-03-01 09:00\n",
        "S1,1001,2.00,MXN,2025-03-02,0\nS2,,5.00,MXN,2025-03-02,0\n",
    )
    cfg = Config(ops_path=ops, billing_path=billing)
    ops_raw, billing_raw = load_ops(cfg), load_billing(cfg)
    assert list(ops_raw["transaction_id"]) == ["00123", "1001"]
    # A blank ref used to turn the whole column into floats ('1001.0').
    assert list(billing_raw["transaction_ref"]) == ["1001", ""]


def test_missing_columns_fail_fast(tmp_path: Path) -> None:
    (tmp_path / "ops.csv").write_text("transaction_id,merchant,amount\nT1,A,1\n", encoding="utf-8")
    (tmp_path / "billing.csv").write_text("statement_id\n", encoding="utf-8")
    cfg = Config(ops_path=tmp_path / "ops.csv", billing_path=tmp_path / "billing.csv")
    with pytest.raises(ValueError, match=r"\[ops\] Missing expected columns"):
        load_ops(cfg)
    with pytest.raises(ValueError, match=r"\[billing\] Missing expected columns"):
        load_billing(cfg)


def test_clean_ops_normalizes_and_rejects_with_reasons() -> None:
    raw = pd.DataFrame(
        {
            "transaction_id": [" t1 ", "", "T3", "T4"],
            "merchant": [" Store ", "A", "B", "C"],
            "channel": ["OXXO"] * 4,
            "amount": ["1,250.00", "999.00", "abc", ""],
            "currency": [" mxn", "MXN", "MXN", "MXN"],
            "status": [" Refunded ", "captured", "captured", "captured"],
            "recorded_at": ["2025-03-01 09:00", "2025-03-01 09:00", "not a date", ""],
        }
    )
    clean, rejected = clean_ops(raw)

    assert list(clean["transaction_id"]) == ["T1"]
    row = clean.iloc[0]
    assert (row["merchant"], row["currency"], row["status"]) == ("Store", "MXN", "refunded")
    assert row["amount_cents"] == 125000

    assert list(rejected["row_number"]) == [2, 3, 4]
    assert list(rejected["reason"]) == [
        "missing transaction_id",
        "unparseable amount",
        "missing amount",
    ]
    # The blank-ID row keeps its parsed amount so the report can total it.
    assert rejected["parsed_amount_cents"].iloc[0] == 99900
    assert rejected["parsed_amount_cents"].iloc[1:].isna().all()


def test_clean_ops_combines_reasons() -> None:
    raw = pd.DataFrame(
        {
            "transaction_id": [""],
            "merchant": ["A"],
            "channel": ["OXXO"],
            "amount": ["x"],
            "currency": ["MXN"],
            "status": ["captured"],
            "recorded_at": [""],
        }
    )
    _, rejected = clean_ops(raw)
    assert rejected["reason"].iloc[0] == "missing transaction_id; unparseable amount"


def test_unparseable_timestamp_is_kept_for_reconciliation() -> None:
    raw = pd.DataFrame(
        {
            "transaction_id": ["T1"],
            "merchant": ["A"],
            "channel": ["OXXO"],
            "amount": ["5.00"],
            "currency": ["MXN"],
            "status": ["captured"],
            "recorded_at": ["yesterday"],
        }
    )
    clean, rejected = clean_ops(raw)
    assert rejected.empty
    assert clean["recorded_at"].isna().all()


def test_clean_billing_rejects_blank_reference() -> None:
    raw = pd.DataFrame(
        {
            "statement_id": ["S1", "S2"],
            "transaction_ref": [" t1", "  "],
            "settlement_amount": ["100.00", "500.00"],
            "currency": ["mxn", "MXN"],
        }
    )
    clean, rejected = clean_billing(raw)
    assert list(clean["transaction_ref"]) == ["T1"]
    assert list(clean["currency"]) == ["MXN"]
    assert rejected[["statement_id", "reason"]].to_dict("records") == [
        {"statement_id": "S2", "reason": "missing transaction_ref"}
    ]
    assert rejected["parsed_amount_cents"].iloc[0] == 50000


@pytest.mark.parametrize(("value", "cents"), [("0", 0), ("0.01", 1), (0.05, 5), ("2", 200)])
def test_tolerance_in_cents(value: object, cents: int) -> None:
    cfg = Config(ops_path=Path("o.csv"), billing_path=Path("b.csv"), amount_tolerance=value)
    assert cfg.tolerance_cents == cents


@pytest.mark.parametrize("value", ["-1", "-0.01", "0.005", "abc", "nan", "inf"])
def test_invalid_tolerance_is_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="tolerance"):
        Config(ops_path=Path("o.csv"), billing_path=Path("b.csv"), amount_tolerance=value)


def test_invalid_config_values() -> None:
    with pytest.raises(ValueError, match="duplicate_window_minutes"):
        Config(ops_path=Path("o.csv"), billing_path=Path("b.csv"), duplicate_window_minutes=-1)
    with pytest.raises(ValueError, match="engine"):
        Config(ops_path=Path("o.csv"), billing_path=Path("b.csv"), engine="spark")
