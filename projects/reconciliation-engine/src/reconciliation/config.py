"""Central configuration: tolerances, expected schemas and paths.

Every threshold lives here so finance can tighten or relax rules without
touching the detection logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Money is compared at cent level; anything FLOAT_TOLERANCE smaller is noise.
FLOAT_TOLERANCE = 0.01

OPS_COLUMNS = [
    "transaction_id",
    "merchant",
    "channel",
    "amount",
    "currency",
    "status",
    "recorded_at",
]

BILLING_COLUMNS = [
    "statement_id",
    "transaction_ref",
    "settlement_amount",
    "currency",
    "settled_at",
    "processor_fee",
]

# Ops rows that never settle are only "orphans" if money moved; refunds cancel.
OPS_ORPHAN_STATUS_EXCLUDE = {"refunded", "cancelled", "void"}


@dataclass
class Config:
    ops_path: Path = Path("data/ops_transactions.csv")
    billing_path: Path = Path("data/billing_statements.csv")
    output_dir: Path = Path("output")

    # An amount difference <= amount_tolerance is considered noise, not a defect.
    amount_tolerance: float = FLOAT_TOLERANCE

    # Two ops rows with the same merchant AND amount AND calendar day are
    # suspected duplicate charges (real merchants rarely sell identical carts).
    duplicate_ops_same_day: bool = True

    extra: dict = field(default_factory=dict)
