"""CSV ingestion with schema validation.

Fail loudly and early: a reconciliation tool that silently swallows a missing
column is worse than one that crashes, because it would assert false peace of
mind to the finance team.
"""

from __future__ import annotations

import pandas as pd

from .config import Config, BILLING_COLUMNS, OPS_COLUMNS


def _validate(path: pd, columns: list[str], source: str) -> None:
    missing = [c for c in columns if c not in path.columns]
    if missing:
        raise ValueError(f"[{source}] Missing expected columns: {missing}")


def load_ops(cfg: Config) -> pd.DataFrame:
    ops = pd.read_csv(cfg.ops_path)
    _validate(ops, OPS_COLUMNS, "ops")
    return ops


def load_billing(cfg: Config) -> pd.DataFrame:
    billing = pd.read_csv(cfg.billing_path)
    _validate(billing, BILLING_COLUMNS, "billing")
    return billing
