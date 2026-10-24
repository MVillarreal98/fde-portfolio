"""Shared fixtures. `src/` is put on the path so the suite runs without installing."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pandas as pd
import pytest

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "src"))

from reconciliation import Config, ReconciliationResult, run_reconciliation  # noqa: E402

DATA = PROJECT / "data"
SAMPLE_OUTPUT = PROJECT / "sample_output"
OPS_HEADER = "transaction_id,merchant,channel,amount,currency,status,recorded_at\n"
BILLING_HEADER = (
    "statement_id,transaction_ref,settlement_amount,currency,settled_at,processor_fee\n"
)

RunCase = Callable[..., ReconciliationResult]


def write_case(directory: Path, ops_rows: str, billing_rows: str) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    ops, billing = directory / "ops.csv", directory / "billing.csv"
    ops.write_text(OPS_HEADER + ops_rows, encoding="utf-8")
    billing.write_text(BILLING_HEADER + billing_rows, encoding="utf-8")
    return ops, billing


def records(df: pd.DataFrame) -> list[tuple]:
    """Engine-neutral rows: numpy/pandas scalars become plain Python values."""

    def norm(value: object) -> object:
        if isinstance(value, pd.Timestamp):
            return value.isoformat()
        if pd.api.types.is_scalar(value) and pd.isna(value):
            return None
        if hasattr(value, "item"):  # numpy scalar
            return value.item()
        return value

    return [tuple(norm(v) for v in row) for row in df.itertuples(index=False)]


@pytest.fixture(params=["pandas", "sql"])
def engine(request: pytest.FixtureRequest) -> str:
    return request.param


@pytest.fixture()
def run_case(tmp_path: Path, engine: str) -> RunCase:
    """Write ops/billing CSV rows to tmp_path and reconcile them with the current engine."""

    def _run(ops_rows: str, billing_rows: str, **cfg_kwargs: object) -> ReconciliationResult:
        ops, billing = write_case(tmp_path / "in", ops_rows, billing_rows)
        cfg = Config(
            ops_path=ops,
            billing_path=billing,
            output_dir=tmp_path / "out",
            engine=engine,
            **cfg_kwargs,
        )
        return run_reconciliation(cfg)

    return _run
