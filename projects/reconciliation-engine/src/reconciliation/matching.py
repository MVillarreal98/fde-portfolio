"""Cross-source matching strategy (pandas engine).

Both sides are aggregated per transaction reference before joining, so the
join is one-to-one by construction (and validated as such). Totals are
conserved even when a reference repeats on either side:

* ops: one row per transaction_id. A repeated ID is reported by its own rule
  and its amounts are summed, never multiplied by the join.
* billing: settlements are summed per reference, with the entry count and the
  largest number of entries sharing one amount. A repeated amount that pushes
  the total over the charge is the signature of a processor retry; a split
  (50 + 50 for a 100 charge) sums to the charge and is not a duplicate.

Every reference then gets exactly ONE reconciliation status (``classify``).
The rules in ``anomalies`` are views over that status, which keeps one problem
from being counted under two rules. ``sql/matched.sql`` implements the same
logic for the DuckDB engine.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import VOID_STATUSES, Config

MATCHED = "matched"
AMOUNT_MISMATCH = "amount_mismatch"
DUPLICATE_SETTLEMENT = "duplicate_settlement"
CURRENCY_MISMATCH = "currency_mismatch"
SETTLED_BUT_CANCELLED = "settled_but_cancelled"
OPS_ONLY = "ops_only"
BILLING_ONLY = "billing_only"
# Expected, not a finding: a reversed charge that never reached settlement.
CANCELLED_NOT_SETTLED = "cancelled_not_settled"

FINDING_STATUSES = (
    DUPLICATE_SETTLEMENT,
    AMOUNT_MISMATCH,
    CURRENCY_MISMATCH,
    SETTLED_BUT_CANCELLED,
    OPS_ONLY,
    BILLING_ONLY,
)

MATCHED_COLUMNS = [
    "transaction_ref",
    "merchant",
    "channel",
    "status",
    "ops_currency",
    "settlement_currency",
    "has_ops",
    "has_billing",
    "ops_rows",
    "ops_amount_cents",
    "settlement_count",
    "settlement_total_cents",
    "amount_difference_cents",
    "max_repeat",
    "statement_ids",
    "recon_status",
]


def _with_currency_codes(df: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    """Add integer currency codes whose order is the lexicographic order of the labels.

    groupby min/max over strings falls back to Python per group (~2 s per 100k
    rows); over integer codes it is vectorized and gives the same answer.
    """
    codes, labels = pd.factorize(df["currency"], sort=True)
    return df.assign(_currency=codes), np.asarray(labels, dtype=object)


def _decode_currency(agg: pd.DataFrame, labels: np.ndarray, prefix: str) -> pd.DataFrame:
    for end in ("min", "max"):
        agg[f"{prefix}_{end}"] = labels[agg.pop(f"_currency_{end}").to_numpy()]
    return agg


def aggregate_ops(ops: pd.DataFrame) -> pd.DataFrame:
    """One row per transaction_id; descriptive fields come from its first row in file order."""
    coded, labels = _with_currency_codes(ops)
    agg = coded.groupby("transaction_id", sort=True).agg(
        merchant=("merchant", "first"),
        channel=("channel", "first"),
        status=("status", "first"),
        _currency_min=("_currency", "min"),
        _currency_max=("_currency", "max"),
        ops_rows=("amount_cents", "size"),
        ops_amount_cents=("amount_cents", "sum"),
    )
    agg = _decode_currency(agg, labels, "ops_currency")
    return agg.rename_axis("transaction_ref").reset_index()


def aggregate_billing(billing: pd.DataFrame) -> pd.DataFrame:
    """Sum settlements per transaction reference and count entries.

    Vectorized: the only per-group Python call builds the statement-id list,
    and it runs only on references that repeat, not on every reference.
    """
    repeats = billing.groupby(["transaction_ref", "amount_cents"])["amount_cents"].transform("size")
    coded, labels = _with_currency_codes(billing.assign(_repeat=repeats))
    agg = coded.groupby("transaction_ref", sort=True).agg(
        _currency_min=("_currency", "min"),
        _currency_max=("_currency", "max"),
        settlement_count=("amount_cents", "size"),
        settlement_total_cents=("amount_cents", "sum"),
        max_repeat=("_repeat", "max"),
        statement_ids=("statement_id", "first"),
    )
    agg = _decode_currency(agg, labels, "settlement_currency")
    multi = billing[billing["transaction_ref"].duplicated(keep=False)]
    if not multi.empty:
        joined = multi.groupby("transaction_ref", sort=True)["statement_id"].agg(", ".join)
        agg.loc[joined.index, "statement_ids"] = joined
    return agg.rename_axis("transaction_ref").reset_index()


def _currency_label(low: pd.Series, high: pd.Series, present: pd.Series) -> pd.Series:
    """'MXN' when one currency, 'MXN/USD' when the side mixes several, None when absent."""
    label = low.astype(object).where(present, None)
    mixed = present & (low != high)
    label[mixed] = low[mixed] + "/" + high[mixed]
    return label


def classify(m: pd.DataFrame, tolerance_cents: int) -> np.ndarray:
    """Assign each reference one status; the first condition that holds wins."""
    both = m["has_ops"] & m["has_billing"]
    void = m["status"].isin(sorted(VOID_STATUSES))
    off = m["amount_difference_cents"].abs() > tolerance_cents
    currency_bad = both & (
        (m["ops_currency_min"] != m["ops_currency_max"])
        | (m["settlement_currency_min"] != m["settlement_currency_max"])
        | (m["ops_currency_min"] != m["settlement_currency_min"])
    )
    conditions = [
        ~m["has_billing"] & void,
        ~m["has_billing"],
        ~m["has_ops"],
        currency_bad,
        void & (m["settlement_total_cents"].abs() > tolerance_cents),
        void,  # reversed in the settlement file: nets to zero, nothing to chase
        off & (m["max_repeat"] > 1),
        off,
    ]
    choices = [
        CANCELLED_NOT_SETTLED,
        OPS_ONLY,
        BILLING_ONLY,
        CURRENCY_MISMATCH,
        SETTLED_BUT_CANCELLED,
        MATCHED,
        DUPLICATE_SETTLEMENT,
        AMOUNT_MISMATCH,
    ]
    return np.select(conditions, choices, default=MATCHED)


def match_sources(ops_agg: pd.DataFrame, billing_agg: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Outer-join the two aggregates (one-to-one) and classify every reference."""
    counts = [
        "ops_rows",
        "ops_amount_cents",
        "settlement_count",
        "settlement_total_cents",
        "max_repeat",
    ]
    # Nullable Int64 so the outer join's missing side never turns cents into floats.
    m = ops_agg.astype({c: "Int64" for c in counts if c in ops_agg}).merge(
        billing_agg.astype({c: "Int64" for c in counts if c in billing_agg}),
        on="transaction_ref",
        how="outer",
        indicator=True,
        validate="one_to_one",
    )
    m["has_ops"] = (m["_merge"] != "right_only").to_numpy(dtype=bool)
    m["has_billing"] = (m["_merge"] != "left_only").to_numpy(dtype=bool)
    for col in counts:
        m[col] = m[col].fillna(0).astype("int64")
    m["amount_difference_cents"] = m["settlement_total_cents"] - m["ops_amount_cents"]
    m["ops_currency"] = _currency_label(m["ops_currency_min"], m["ops_currency_max"], m["has_ops"])
    m["settlement_currency"] = _currency_label(
        m["settlement_currency_min"], m["settlement_currency_max"], m["has_billing"]
    )
    m["recon_status"] = classify(m, cfg.tolerance_cents)
    return m[MATCHED_COLUMNS].sort_values("transaction_ref").reset_index(drop=True)
