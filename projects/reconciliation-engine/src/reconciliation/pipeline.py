"""End-to-end pipeline wiring: load → clean → match → detect → report."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .anomalies import run_detectors
from .cleaning import clean_billing, clean_ops
from .loaders import load_billing, load_ops
from .matching import aggregate_billing, match_sources
from .report import export_findings_csv, export_report


@dataclass
class ReconciliationResult:
    matched: pd.DataFrame
    findings: dict[str, pd.DataFrame]
    report_path: str
    csv_paths: list[str]


def run_reconciliation(cfg) -> ReconciliationResult:
    ops = clean_ops(load_ops(cfg), cfg)
    billing = clean_billing(load_billing(cfg), cfg)
    agg = aggregate_billing(billing)
    matched = match_sources(ops, agg)
    findings = run_detectors(matched, ops, cfg)

    report_path = export_report(matched, findings, cfg)
    csv_paths = [str(p) for p in export_findings_csv(findings, cfg)]

    print(f"[ok] Reconciled {len(ops)} ops transactions vs {len(billing)} billing rows.")
    for name, df in findings.items():
        print(f"[!] {name}: {len(df)} findings")
    if not findings:
        print("[ok] No anomalies — sources reconcile.")
    print(f"[ok] Executive report: {report_path}")
    return ReconciliationResult(matched, findings, str(report_path), csv_paths)
