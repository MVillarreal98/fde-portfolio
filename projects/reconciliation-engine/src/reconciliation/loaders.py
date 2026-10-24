"""CSV ingestion with schema validation.

Fail loudly and early: a reconciliation tool that silently swallows a missing
column is worse than one that crashes, because it would assert false peace of
mind to the finance team.

Every column is read as text (``dtype=str``, no NA inference) so identifiers
keep their exact spelling: '00123' stays '00123' and '1001' never becomes
'1001.0'. Typing (money, timestamps) happens in ``cleaning`` where failures are
recorded as rejected rows instead of being coerced away.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import BILLING_COLUMNS, OPS_COLUMNS, Config


def _validate(df: pd.DataFrame, columns: list[str], source: str) -> None:
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"[{source}] Missing expected columns: {missing}")


def read_source(path: Path, columns: list[str], source: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df.columns = [str(c).strip() for c in df.columns]
    _validate(df, columns, source)
    # Short rows still come back as NaN even with keep_default_na=False.
    return df.fillna("")


def load_ops(cfg: Config) -> pd.DataFrame:
    return read_source(cfg.ops_path, OPS_COLUMNS, "ops")


def load_billing(cfg: Config) -> pd.DataFrame:
    return read_source(cfg.billing_path, BILLING_COLUMNS, "billing")
