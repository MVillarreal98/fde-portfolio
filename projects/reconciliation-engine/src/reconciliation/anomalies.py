"""Anomaly detection rules.

Each rule is a pure function over the matched table so it can be tested and
extended independently. New rules plug into ANOMALY_RULES and the pipeline
picks them up automatically.
"""

from __future__ import annotations

import pandas as pd

from .config import Config, OPS_ORPHAN_STATUS_EXCLUDE


def rule_duplicate_settlements(matched: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Same transaction settled more than once (processor retry billing twice)."""
    dupes = matched[matched["settlement_count"] > 1].copy()
    if dupes.empty:
        return pd.DataFrame()
    return dupes[[
        "transaction_ref", "merchant", "settlement_count",
        "statement_ids", "settlement_total",
    ]]


def rule_amount_mismatch(matched: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """Settled total differs from the recorded amount beyond tolerance.

    Only transactions that appeared on both sides can mismatch; the difference
    direction goes in a dedicated column so finance can sort by loss value.
    """
    both = matched[matched["settlement_count"] > 0].copy()
    both["amount_difference"] = (both["settlement_total"] - both["ops_amount"]).round(2)
    bad = both[both["amount_difference"].abs() > cfg.amount_tolerance]
    if bad.empty:
        return pd.DataFrame()
    bad["amount_difference"] = bad["amount_difference"]
    return bad[[
        "transaction_ref", "merchant", "channel", "ops_amount",
        "settlement_total", "amount_difference",
    ]].sort_values("amount_difference", key=lambda s: s.abs(), ascending=False)


def rule_orphans(matched: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """One-sided records: recorded-but-never-settled or settled-but-never-recorded."""
    ops_only = (matched["settlement_count"] == 0) & (matched["ops_amount"] > 0)
    billing_only = (matched["settlement_count"] > 0) & (matched["ops_amount"] == 0)
    orphans = matched[ops_only | billing_only].copy()

    # Refunds/cancelled ops entries that never settle are expected behavior.
    orphans = orphans[~orphans["status"].isin(OPS_ORPHAN_STATUS_EXCLUDE)]
    if orphans.empty:
        return pd.DataFrame()
    orphans["discrepancy_type"] = orphans.apply(
        lambda r: (
            "ops_without_settlement (possible revenue leakage)"
            if r["ops_amount"] > 0
            else "settlement_without_ops_record (possible phantom revenue)"
        ),
        axis=1,
    )
    return orphans[[
        "transaction_ref", "merchant", "channel",
        "ops_amount", "settlement_total", "discrepancy_type",
    ]]


def rule_duplicate_ops_entries(ops: pd.DataFrame, cfg: Config) -> pd.DataFrame:
    """The same charge captured more than once in the system of record.

    Heuristic: identical merchant + amount + calendar day. Real merchants
    rarely record two identical charges the same day by coincidence.
    """
    if not cfg.duplicate_ops_same_day:
        return pd.DataFrame()
    dupes = ops[ops.duplicated(subset=["merchant", "amount", "recorded_date"], keep=False)]
    if dupes.empty:
        return pd.DataFrame()
    grouped = (
        dupes.groupby(["merchant", "amount", "recorded_date"], as_index=False)
        .agg(transaction_ids=("transaction_id", ", ".join), occurrences=("transaction_id", "size"))
        .sort_values("occurrences", ascending=False)
    )
    return grouped


ANOMALY_RULES = {
    "duplicate_settlements": rule_duplicate_settlements,
    "amount_mismatch": rule_amount_mismatch,
    "orphans": rule_orphans,
}


def run_detectors(matched: pd.DataFrame, ops: pd.DataFrame, cfg: Config) -> dict[str, pd.DataFrame]:
    findings: dict[str, pd.DataFrame] = {
        name: rule(matched, cfg) for name, rule in ANOMALY_RULES.items()
    }
    ops_dupes = rule_duplicate_ops_entries(ops, cfg)
    if not ops_dupes.empty:
        findings["duplicate_ops_entries"] = ops_dupes
    # Keep only rules that actually fired so the report stays readable.
    return {name: df for name, df in findings.items() if not df.empty}
