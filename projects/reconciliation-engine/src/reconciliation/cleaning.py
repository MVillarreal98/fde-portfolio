"""Cleaning: normalize both sources to comparable form.

Real exports always arrive dirty (trailing spaces, mixed date formats, stray
zeros). Cleaning lives between ingestion and detection so every rule downstream
operates on the same normalized shape.
"""

from __future__ import annotations

import pandas as pd

from .config import Config


def clean_ops(ops: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    ops = ops.copy()
    ops["transaction_id"] = ops["transaction_id"].astype(str).str.strip().str.upper()
    ops["merchant"] = ops["merchant"].astype(str).str.strip()
    ops["amount"] = pd.to_numeric(ops["amount"], errors="coerce").round(2)
    ops["currency"] = ops["currency"].astype(str).str.strip().str.upper()
    ops["recorded_at"] = pd.to_datetime(ops["recorded_at"], errors="coerce")

    # Records without a usable ID or amount cannot be reconciled: report-drop.
    bad = ops["transaction_id"].isin(["", "NAN"]) | ops["amount"].isna()
    ops = ops[~bad].copy()
    ops["recorded_date"] = ops["recorded_at"].dt.date
    return ops.reset_index(drop=True)


def clean_billing(billing: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    billing = billing.copy()
    billing["transaction_ref"] = (
        billing["transaction_ref"].astype(str).str.strip().str.upper()
    )
    billing["settlement_amount"] = (
        pd.to_numeric(billing["settlement_amount"], errors="coerce").round(2)
    )
    billing["currency"] = billing["currency"].astype(str).str.strip().str.upper()
    billing.dropna(subset=["settlement_amount"], inplace=True)
    billing = billing[billing["transaction_ref"].notna()]
    return billing.reset_index(drop=True)
