"""DuckDB engine: the same matching and rules, written as plain SQL.

The queries live in ``reconciliation/sql/*.sql`` so they can be read, reviewed
and run on their own. This module only loads the cleaned inputs into an
in-memory DuckDB database, sets the parameters and runs the files in order.

Ingestion, money parsing and row rejection are shared with the pandas engine,
so both engines reconcile exactly the same rows; the test suite asserts they
return identical findings.
"""

from __future__ import annotations

from importlib.resources import files

import duckdb
import pandas as pd

from .anomalies import RULE_COLUMNS
from .config import VOID_STATUSES, Config

OPS_INPUT = [
    "row_number",
    "transaction_id",
    "merchant",
    "channel",
    "currency",
    "status",
    "recorded_at",
    "amount_cents",
]
BILLING_INPUT = ["row_number", "statement_id", "transaction_ref", "currency", "amount_cents"]


def read_sql(name: str) -> str:
    return (files("reconciliation") / "sql" / f"{name}.sql").read_text(encoding="utf-8")


def _sql_list(values: frozenset[str]) -> str:
    return "[" + ", ".join("'" + v.replace("'", "''") + "'" for v in sorted(values)) + "]"


def reconcile_sql(
    ops: pd.DataFrame, billing: pd.DataFrame, cfg: Config
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """Run sql/matched.sql, then one sql/<rule>.sql per rule. Returns (matched, findings)."""
    con = duckdb.connect(":memory:")
    try:
        con.register("ops", ops[OPS_INPUT])
        con.register("billing", billing[BILLING_INPUT])
        # Integers validated by Config and constant status names: safe to inline.
        con.execute(f"SET VARIABLE tolerance_cents = {int(cfg.tolerance_cents)}")
        con.execute(f"SET VARIABLE window_minutes = {int(cfg.duplicate_window_minutes)}")
        con.execute(f"SET VARIABLE void_statuses = {_sql_list(VOID_STATUSES)}")
        con.execute(read_sql("matched"))
        matched = con.execute("SELECT * FROM matched ORDER BY transaction_ref").df()
        findings = {name: con.execute(read_sql(name)).df() for name in RULE_COLUMNS}
    finally:
        con.close()
    return matched, findings
