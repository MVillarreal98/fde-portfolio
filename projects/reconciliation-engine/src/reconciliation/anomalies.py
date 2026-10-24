"""Anomaly detection rules (pandas engine).

Every rule has the same signature ``rule(matched, ops, billing, cfg)`` and
returns a DataFrame with the fixed columns listed in RULE_COLUMNS (empty when
nothing fires), so new rules plug into ANOMALY_RULES and the pipeline picks
them up. ``sql/<rule>.sql`` holds the DuckDB version of each rule and the test
suite asserts that both engines return identical findings.

The first five rules are views over the single reconciliation status assigned
in ``matching.classify``, so a reference appears under at most one of them.
The last two inspect raw ops rows (ledger integrity) and may overlap with the
others on purpose: they explain *why* a reference does not reconcile.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd

from .config import Config
from .matching import (
    AMOUNT_MISMATCH,
    BILLING_ONLY,
    CURRENCY_MISMATCH,
    DUPLICATE_SETTLEMENT,
    OPS_ONLY,
    SETTLED_BUT_CANCELLED,
)

LEAKAGE = "ops_without_settlement (possible revenue leakage)"
UNSETTLED_REFUND = "ops_without_settlement (negative amount: refund never settled)"
PHANTOM = "settlement_without_ops_record (possible phantom revenue)"

RULE_COLUMNS: dict[str, list[str]] = {
    "duplicate_settlements": [
        "transaction_ref",
        "merchant",
        "channel",
        "ops_amount_cents",
        "settlement_total_cents",
        "amount_difference_cents",
        "settlement_count",
        "statement_ids",
    ],
    "amount_mismatch": [
        "transaction_ref",
        "merchant",
        "channel",
        "ops_amount_cents",
        "settlement_total_cents",
        "amount_difference_cents",
    ],
    "currency_mismatch": [
        "transaction_ref",
        "merchant",
        "channel",
        "ops_currency",
        "settlement_currency",
        "ops_amount_cents",
        "settlement_total_cents",
    ],
    "settled_but_cancelled": [
        "transaction_ref",
        "merchant",
        "channel",
        "status",
        "ops_amount_cents",
        "settlement_total_cents",
        "statement_ids",
    ],
    "orphans": [
        "transaction_ref",
        "merchant",
        "channel",
        "ops_amount_cents",
        "settlement_total_cents",
        "discrepancy_type",
    ],
    "duplicate_ops_ids": [
        "transaction_id",
        "occurrences",
        "ops_amount_total_cents",
        "row_numbers",
    ],
    "duplicate_charge_candidates": [
        "merchant",
        "channel",
        "amount_cents",
        "occurrences",
        "settled_count",
        "transaction_ids",
        "first_recorded_at",
        "last_recorded_at",
    ],
}


def _view(matched: pd.DataFrame, statuses: list[str]) -> pd.DataFrame:
    return matched[matched["recon_status"].isin(statuses)].reset_index(drop=True)


def rule_duplicate_settlements(
    matched: pd.DataFrame, ops: pd.DataFrame, billing: pd.DataFrame, cfg: Config
) -> pd.DataFrame:
    """Same amount settled more than once for a reference, pushing the total off the charge.

    A legitimate split (50 + 50 for a 100 charge) sums to the recorded amount
    and is not flagged, even though the two parts share an amount.
    """
    df = _view(matched, [DUPLICATE_SETTLEMENT])
    return df[RULE_COLUMNS["duplicate_settlements"]]


def rule_amount_mismatch(
    matched: pd.DataFrame, ops: pd.DataFrame, billing: pd.DataFrame, cfg: Config
) -> pd.DataFrame:
    """Settled total differs from the recorded amount beyond tolerance.

    Only references present on BOTH sides can mismatch (one-sided ones are
    orphans). Sorted by absolute difference so finance starts with the biggest.
    """
    df = _view(matched, [AMOUNT_MISMATCH])
    df = df.assign(_abs=df["amount_difference_cents"].abs()).sort_values(
        ["_abs", "transaction_ref"], ascending=[False, True], kind="mergesort"
    )
    return df[RULE_COLUMNS["amount_mismatch"]].reset_index(drop=True)


def rule_currency_mismatch(
    matched: pd.DataFrame, ops: pd.DataFrame, billing: pd.DataFrame, cfg: Config
) -> pd.DataFrame:
    """Ops and billing disagree on currency (or one side mixes currencies).

    Amounts in different currencies are not comparable, so these references
    are never reported as amount mismatches.
    """
    df = _view(matched, [CURRENCY_MISMATCH])
    return df[RULE_COLUMNS["currency_mismatch"]]


def rule_settled_but_cancelled(
    matched: pd.DataFrame, ops: pd.DataFrame, billing: pd.DataFrame, cfg: Config
) -> pd.DataFrame:
    """Refunded/cancelled/void in ops, yet its settlements do not net to zero."""
    df = _view(matched, [SETTLED_BUT_CANCELLED])
    return df[RULE_COLUMNS["settled_but_cancelled"]]


def rule_orphans(
    matched: pd.DataFrame, ops: pd.DataFrame, billing: pd.DataFrame, cfg: Config
) -> pd.DataFrame:
    """One-sided records: recorded-but-never-settled or settled-but-never-recorded.

    Reversed charges (refunded/cancelled/void) that never settle are expected
    and excluded upstream (status ``cancelled_not_settled``).
    """
    df = _view(matched, [OPS_ONLY, BILLING_ONLY])
    df["discrepancy_type"] = np.select(
        [df["recon_status"] == BILLING_ONLY, df["ops_amount_cents"] < 0],
        [PHANTOM, UNSETTLED_REFUND],
        default=LEAKAGE,
    )
    return df[RULE_COLUMNS["orphans"]]


def rule_duplicate_ops_ids(
    matched: pd.DataFrame, ops: pd.DataFrame, billing: pd.DataFrame, cfg: Config
) -> pd.DataFrame:
    """The same transaction_id appears more than once in the system of record.

    Matching sums the repeated rows, so totals stay correct; this rule makes the
    repetition visible with the file row numbers to fix at the source.
    """
    dup = ops[ops["transaction_id"].duplicated(keep=False)]
    out = (
        dup.assign(row_numbers=dup["row_number"].astype(str))
        .groupby("transaction_id", sort=True)
        .agg(
            occurrences=("row_number", "size"),
            ops_amount_total_cents=("amount_cents", "sum"),
            row_numbers=("row_numbers", ", ".join),
        )
        .reset_index()
    )
    return out.reindex(columns=RULE_COLUMNS["duplicate_ops_ids"])


def rule_duplicate_charge_candidates(
    matched: pd.DataFrame, ops: pd.DataFrame, billing: pd.DataFrame, cfg: Config
) -> pd.DataFrame:
    """Repeated captures that look like one payment recorded twice.

    Identical cash payments at the same store on the same day are normal, so an
    identical amount alone is not evidence. A group is formed by captures with
    the same merchant, channel and amount, each recorded within
    ``duplicate_window_minutes`` of the previous one (chained). The group is
    reported only when it has fewer settled captures than captures: a double
    capture in the ledger settles once, two real payments settle twice. Rows
    without a parseable recorded_at are left out of this heuristic.
    """
    keys = ["merchant", "channel", "amount_cents"]
    cols = RULE_COLUMNS["duplicate_charge_candidates"]
    c = ops[ops["recorded_at"].notna()].sort_values(
        keys + ["recorded_at", "row_number"], kind="mergesort"
    )
    if c.empty:
        return pd.DataFrame(columns=cols)
    same_key = (c[keys] == c[keys].shift()).all(axis=1)
    # numpy compare: exact across ns/us resolutions and free of the pandas 2.3 +
    # numpy 2.5 "generic timedelta unit" deprecation that Series > Timedelta hits.
    window = np.timedelta64(cfg.duplicate_window_minutes, "m")
    too_far = c["recorded_at"].diff().to_numpy() > window
    group = (~same_key | too_far).cumsum()
    settled = c["transaction_id"].isin(billing["transaction_ref"])
    size = group.groupby(group).transform("size")
    settled_in_group = settled.groupby(group).transform("sum")
    flagged = c.assign(_group=group, _settled=settled)[(size >= 2) & (settled_in_group < size)]
    out = flagged.groupby("_group", sort=False).agg(
        merchant=("merchant", "first"),
        channel=("channel", "first"),
        amount_cents=("amount_cents", "first"),
        occurrences=("transaction_id", "size"),
        settled_count=("_settled", "sum"),
        transaction_ids=("transaction_id", ", ".join),
        first_recorded_at=("recorded_at", "min"),
        last_recorded_at=("recorded_at", "max"),
    )
    out = out.sort_values(["merchant", "channel", "amount_cents", "first_recorded_at"])
    return out.reset_index(drop=True).reindex(columns=cols)


Rule = Callable[[pd.DataFrame, pd.DataFrame, pd.DataFrame, Config], pd.DataFrame]

ANOMALY_RULES: dict[str, Rule] = {
    "duplicate_settlements": rule_duplicate_settlements,
    "amount_mismatch": rule_amount_mismatch,
    "currency_mismatch": rule_currency_mismatch,
    "settled_but_cancelled": rule_settled_but_cancelled,
    "orphans": rule_orphans,
    "duplicate_ops_ids": rule_duplicate_ops_ids,
    "duplicate_charge_candidates": rule_duplicate_charge_candidates,
}


def run_detectors(
    matched: pd.DataFrame, ops: pd.DataFrame, billing: pd.DataFrame, cfg: Config
) -> dict[str, pd.DataFrame]:
    """Run every registered rule. Rules that did not fire come back empty, not missing."""
    return {name: rule(matched, ops, billing, cfg) for name, rule in ANOMALY_RULES.items()}
