"""Cross-source matching strategy.

Assumption of the reconciliation model: one operational transaction settles at
most once, but settlement files frequently arrive with repeated entries
(processor retries) or partial groupings. Therefore we aggregate billing by
transaction reference and reconcile the aggregate against the ops amount.
"""

from __future__ import annotations

import pandas as pd


def aggregate_billing(billing: pd.DataFrame) -> pd.DataFrame:
    """Sum settlements per transaction reference and count entries.

    Contextual columns (settled dates, statement ids) are aggregated when
    present, so tests and callers can pass minimal frames.
    """
    agg_spec: dict = {
        "settlement_total": ("settlement_amount", "sum"),
        "settlement_count": ("settlement_amount", "size"),
    }
    if "settled_at" in billing.columns:
        agg_spec["settled_dates"] = (
            "settled_at", lambda s: ", ".join(sorted(s.astype(str)))
        )
    if "statement_id" in billing.columns:
        agg_spec["statement_ids"] = (
            "statement_id", lambda s: ", ".join(map(str, s))
        )
    agg = billing.groupby("transaction_ref", as_index=False).agg(**agg_spec)
    return agg


def match_sources(ops: pd.DataFrame, agg: pd.DataFrame) -> pd.DataFrame:
    """Outer-join ops ledger to the billing aggregate, keyed by transaction."""
    ops_min = ops[
        ["transaction_id", "merchant", "channel", "amount", "currency", "status", "recorded_date"]
    ].rename(columns={"transaction_id": "transaction_ref", "amount": "ops_amount"})
    matched = ops_min.merge(agg, on="transaction_ref", how="outer")
    matched["ops_amount"] = matched["ops_amount"].fillna(0.0)
    matched["settlement_total"] = matched["settlement_total"].fillna(0.0)
    matched["settlement_count"] = matched["settlement_count"].fillna(0).astype(int)
    return matched.sort_values("transaction_ref").reset_index(drop=True)
