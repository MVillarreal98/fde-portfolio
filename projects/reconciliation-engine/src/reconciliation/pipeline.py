"""End-to-end pipeline wiring: load → clean → match → detect → report.

Two conservation checks guard the money path. If either fails, the run stops
with ReconciliationIntegrityError instead of publishing a report that does not
add up:

1. per source, rows read == rows processed + rows rejected, and the sum of
   every parseable amount read == processed amount + rejected amount;
2. after matching, the matched table carries exactly the processed rows and
   amounts of each source (nothing lost or multiplied by the join).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from .anomalies import run_detectors
from .cleaning import REJECTED_COLUMNS, clean_billing, clean_ops, parse_amount_cents
from .config import Config
from .loaders import load_billing, load_ops
from .matching import aggregate_billing, aggregate_ops, match_sources
from .report import export_findings_csv, export_rejected_csv, export_report

log = logging.getLogger(__name__)

Engine = Callable[
    [pd.DataFrame, pd.DataFrame, Config], tuple[pd.DataFrame, dict[str, pd.DataFrame]]
]


class ReconciliationIntegrityError(RuntimeError):
    """A conservation invariant failed: the report would not add up."""


@dataclass
class SourceStats:
    source: str
    rows_read: int
    rows_processed: int
    rows_rejected: int
    amount_read_cents: int  # sum of every amount that could be parsed
    amount_processed_cents: int
    amount_rejected_cents: int
    unparseable_amounts: int


@dataclass
class ReconciliationResult:
    matched: pd.DataFrame
    findings: dict[str, pd.DataFrame]
    rejected: pd.DataFrame
    stats: dict[str, SourceStats]
    report_path: str
    csv_paths: list[str]
    rejected_path: str

    @property
    def fired(self) -> dict[str, pd.DataFrame]:
        return {name: df for name, df in self.findings.items() if not df.empty}

    @property
    def needs_attention(self) -> bool:
        return bool(self.fired) or not self.rejected.empty


def source_stats(
    source: str, raw_amounts: pd.Series, clean: pd.DataFrame, rejected: pd.DataFrame
) -> SourceStats:
    """Count rows and money on both sides of the clean/rejected split and check they add up.

    The amount read is re-parsed from the raw column, independently of the split.
    """
    read_cents, _ = parse_amount_cents(raw_amounts)
    stats = SourceStats(
        source=source,
        rows_read=len(raw_amounts),
        rows_processed=len(clean),
        rows_rejected=len(rejected),
        amount_read_cents=int(read_cents.sum()),
        amount_processed_cents=int(clean["amount_cents"].sum()),
        amount_rejected_cents=int(rejected["parsed_amount_cents"].sum()),
        unparseable_amounts=int(rejected["parsed_amount_cents"].isna().sum()),
    )
    if stats.rows_read != stats.rows_processed + stats.rows_rejected:
        raise ReconciliationIntegrityError(
            f"[{source}] rows read {stats.rows_read} != processed {stats.rows_processed}"
            f" + rejected {stats.rows_rejected}"
        )
    if stats.amount_read_cents != stats.amount_processed_cents + stats.amount_rejected_cents:
        raise ReconciliationIntegrityError(
            f"[{source}] amount read {stats.amount_read_cents} cents != processed"
            f" {stats.amount_processed_cents} + rejected {stats.amount_rejected_cents}"
        )
    return stats


def check_matched_conservation(
    matched: pd.DataFrame, ops: pd.DataFrame, billing: pd.DataFrame
) -> None:
    checks = {
        "ops rows": (int(matched["ops_rows"].sum()), len(ops)),
        "ops amount cents": (
            int(matched["ops_amount_cents"].sum()),
            int(ops["amount_cents"].sum()),
        ),
        "billing rows": (int(matched["settlement_count"].sum()), len(billing)),
        "billing amount cents": (
            int(matched["settlement_total_cents"].sum()),
            int(billing["amount_cents"].sum()),
        ),
    }
    broken = [
        f"{k}: matched {got} != processed {want}"
        for k, (got, want) in checks.items()
        if got != want
    ]
    if broken:
        raise ReconciliationIntegrityError(
            "matched table does not conserve inputs: " + "; ".join(broken)
        )


def _pandas_engine(
    ops: pd.DataFrame, billing: pd.DataFrame, cfg: Config
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    matched = match_sources(aggregate_ops(ops), aggregate_billing(billing), cfg)
    return matched, run_detectors(matched, ops, billing, cfg)


def get_engine(name: str) -> Engine:
    if name == "sql":
        from .sql_engine import reconcile_sql  # lazy: duckdb is only loaded when used

        return reconcile_sql
    return _pandas_engine


def _concat_rejected(frames: list[pd.DataFrame]) -> pd.DataFrame:
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame(columns=REJECTED_COLUMNS)
    return pd.concat(frames, ignore_index=True)


def run_reconciliation(cfg: Config) -> ReconciliationResult:
    ops_raw, billing_raw = load_ops(cfg), load_billing(cfg)
    ops, ops_rejected = clean_ops(ops_raw)
    billing, billing_rejected = clean_billing(billing_raw)
    stats = {
        "ops": source_stats("ops", ops_raw["amount"], ops, ops_rejected),
        "billing": source_stats(
            "billing", billing_raw["settlement_amount"], billing, billing_rejected
        ),
    }
    rejected = _concat_rejected([ops_rejected, billing_rejected])
    log.info(
        "Read %d ops rows and %d billing rows; engine=%s",
        len(ops_raw),
        len(billing_raw),
        cfg.engine,
    )
    if not rejected.empty:
        log.warning(
            "Rejected %d ops rows and %d billing rows (see rejected_rows.csv)",
            len(ops_rejected),
            len(billing_rejected),
        )

    matched, findings = get_engine(cfg.engine)(ops, billing, cfg)
    check_matched_conservation(matched, ops, billing)

    report_path = export_report(matched, findings, rejected, stats, cfg)
    csv_paths = [str(p) for p in export_findings_csv(findings, cfg)]
    rejected_path = export_rejected_csv(rejected, cfg)
    result = ReconciliationResult(
        matched, findings, rejected, stats, str(report_path), csv_paths, str(rejected_path)
    )
    for name, df in result.fired.items():
        log.warning("%s: %d findings", name, len(df))
    if not result.fired:
        log.info("No anomalies: sources reconcile within tolerance.")
    log.info("Executive report: %s", report_path)
    return result
