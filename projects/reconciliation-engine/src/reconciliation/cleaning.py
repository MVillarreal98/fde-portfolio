"""Cleaning: normalize both sources and split valid rows from rejected ones.

Real exports arrive dirty (padding spaces, thousands separators, blank keys).
Every row read ends up in exactly one of two places: the clean frame the
engines reconcile, or the rejected frame (written to rejected_rows.csv with a
reason). Nothing is dropped silently.

Money is held as integer cents (int64) from here on; floats never touch it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import BILLING_COLUMNS, OPS_COLUMNS

# Optional sign, integer part with or without thousands separators, optional decimals.
_AMOUNT_RE = r"^(?P<sign>[+-]?)(?P<int>\d{1,3}(?:,\d{3})+|\d+)(?:\.(?P<frac>\d+))?$"
# The shape most exports use; parsed without the regex groups above.
_SIMPLE_AMOUNT_RE = r"-?\d{1,13}\.\d\d"
# 13 integer digits (~10 trillion) keeps cents far below the int64 limit.
_MAX_INT_DIGITS = 13

# transaction_ref is the reconciliation key of either source; statement_id is billing-only.
# parsed_amount_cents is empty when the amount itself could not be parsed.
REJECTED_COLUMNS = [
    "source",
    "row_number",
    "transaction_ref",
    "statement_id",
    "raw_amount",
    "parsed_amount_cents",
    "reason",
]


def parse_amount_cents(raw: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Parse money text into integer cents without going through float.

    Accepts '1250', '1250.5', '1,250.00', '-300.00' and '+12.30'. Digits beyond
    the cents are allowed only when they are zeros ('10.500'); '10.505' is
    rejected rather than rounded. Returns ``(cents, reason)``: ``cents`` is a
    nullable Int64 series and ``reason`` is '' for valid values.
    """
    text = raw.astype(str).str.strip()
    # Fast path for the usual export shape ('-1250.50'): drop the dot, read digits.
    simple = text.str.fullmatch(_SIMPLE_AMOUNT_RE)
    if simple.all():
        cents = pd.to_numeric(text.str.replace(".", "", regex=False)).astype("Int64")
        return cents, pd.Series("", index=raw.index, dtype=object)
    return _parse_general(text)


def _parse_general(text: pd.Series) -> tuple[pd.Series, pd.Series]:
    parts = text.str.extract(_AMOUNT_RE)
    matched = parts["int"].notna()
    int_digits = parts["int"].fillna("").str.replace(",", "", regex=False)
    frac = parts["frac"].fillna("")
    sub_cent = frac.str[2:].str.strip("0") != ""
    too_big = int_digits.str.len() > _MAX_INT_DIGITS

    reason = pd.Series(
        np.select(
            [text == "", ~matched, sub_cent, too_big],
            [
                "missing amount",
                "unparseable amount",
                "amount has sub-cent digits",
                "amount out of range",
            ],
            default="",
        ),
        index=text.index,
    )
    valid = reason == ""
    digits = (int_digits + frac.str[:2].str.ljust(2, "0")).where(valid, "0")
    cents = pd.to_numeric(digits).astype("int64")
    cents = cents.where(parts["sign"].fillna("") != "-", -cents)
    return cents.astype("Int64").where(valid, pd.NA), reason


def _strip_all(raw: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    df = raw[columns].copy()
    for col in columns:
        df[col] = df[col].astype(str).str.strip()
    df.insert(0, "row_number", np.arange(1, len(df) + 1, dtype="int64"))
    return df


def _join_reasons(reasons: list[pd.Series]) -> pd.Series:
    joined = reasons[0]
    for reason in reasons[1:]:
        sep = pd.Series(np.where((joined != "") & (reason != ""), "; ", ""), index=joined.index)
        joined = joined + sep + reason
    return joined


def _split(
    df: pd.DataFrame, reasons: list[pd.Series], source: str, key_col: str, amount_col: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Route every row to the clean frame or to the rejected frame (never both)."""
    reason = _join_reasons(reasons)
    bad = reason != ""
    rejected = pd.DataFrame(
        {
            "source": source,
            "row_number": df.loc[bad, "row_number"],
            "transaction_ref": df.loc[bad, key_col],
            "statement_id": df.loc[bad, "statement_id"] if "statement_id" in df else "",
            "raw_amount": df.loc[bad, amount_col],
            "parsed_amount_cents": df.loc[bad, "amount_cents"],
            "reason": reason[bad],
        },
        columns=REJECTED_COLUMNS,
    )
    clean = df[~bad].drop(columns=amount_col).reset_index(drop=True)
    clean["amount_cents"] = clean["amount_cents"].astype("int64")
    return clean, rejected.reset_index(drop=True)


def clean_ops(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Normalize the ops ledger. Returns ``(clean, rejected)``."""
    ops = _strip_all(raw, OPS_COLUMNS)
    ops["transaction_id"] = ops["transaction_id"].str.upper()
    ops["currency"] = ops["currency"].str.upper()
    ops["status"] = ops["status"].str.lower()
    ops["amount_cents"], amount_reason = parse_amount_cents(ops["amount"])
    # An unparseable timestamp does not block reconciliation; the row only stays
    # out of the duplicate-charge heuristic, which needs a time to compare.
    ops["recorded_at"] = pd.to_datetime(ops["recorded_at"], errors="coerce")
    id_reason = pd.Series(
        np.where(ops["transaction_id"] == "", "missing transaction_id", ""), index=ops.index
    )
    return _split(ops, [id_reason, amount_reason], "ops", "transaction_id", "amount")


def clean_billing(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Normalize the billing/settlement export. Returns ``(clean, rejected)``."""
    billing = _strip_all(raw, BILLING_COLUMNS)
    billing["transaction_ref"] = billing["transaction_ref"].str.upper()
    billing["currency"] = billing["currency"].str.upper()
    billing["amount_cents"], amount_reason = parse_amount_cents(billing["settlement_amount"])
    ref_reason = pd.Series(
        np.where(billing["transaction_ref"] == "", "missing transaction_ref", ""),
        index=billing.index,
    )
    return _split(
        billing, [ref_reason, amount_reason], "billing", "transaction_ref", "settlement_amount"
    )
