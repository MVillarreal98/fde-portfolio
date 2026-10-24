"""Executive report: a Markdown summary, one CSV per rule and rejected_rows.csv.

Money travels through the engines as integer cents; this module is the only
place where cents become text ('1250.00' in CSVs, '$1,250.00' in the summary).
Every rule gets a CSV on every run (header only when it did not fire), so a
downstream job never reads a stale file from a previous run.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from . import __version__
from .anomalies import ANOMALY_RULES
from .config import Config
from .matching import FINDING_STATUSES

if TYPE_CHECKING:  # pragma: no cover
    from .pipeline import SourceStats

STATUS_MEANING = {
    "matched": "Recorded and settled amounts agree within tolerance",
    "cancelled_not_settled": "Reversed in ops and never settled (expected)",
    "duplicate_settlement": "Same amount settled more than once",
    "amount_mismatch": "Settled total differs from recorded amount",
    "currency_mismatch": "Currencies differ between sources",
    "settled_but_cancelled": "Reversed in ops but settlement does not net to zero",
    "ops_only": "Recorded, never settled",
    "billing_only": "Settled, never recorded",
}

MAX_REJECTED_IN_REPORT = 50


def cents_to_text(cents: object) -> str:
    """125000 -> '1250.00'; missing -> ''."""
    if cents is None or pd.isna(cents):
        return ""
    value = int(cents)  # type: ignore[call-overload]
    sign = "-" if value < 0 else ""
    return f"{sign}{abs(value) // 100}.{abs(value) % 100:02d}"


def _fmt_money(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}${abs(cents) // 100:,}.{abs(cents) % 100:02d}"


def to_display(df: pd.DataFrame) -> pd.DataFrame:
    """Copy with ``*_cents`` columns as decimal text (suffix dropped) and timestamps as text."""
    out = df.copy()
    renames = {}
    for col in df.columns:
        if col.endswith("_cents"):
            out[col] = df[col].map(cents_to_text)
            renames[col] = col.removesuffix("_cents")
        elif pd.api.types.is_datetime64_any_dtype(df[col]):
            out[col] = df[col].dt.strftime("%Y-%m-%d %H:%M")
    return out.rename(columns=renames)


def _markdown(df: pd.DataFrame) -> str:
    # disable_numparse keeps '1250.00' and '00123' exactly as written.
    return to_display(df).fillna("—").to_markdown(index=False, disable_numparse=True)


def _currencies(matched: pd.DataFrame) -> str:
    seen: set[str] = set()
    for col in ("ops_currency", "settlement_currency"):
        for label in matched[col].dropna():
            seen.update(label.split("/"))
    return ", ".join(sorted(c or "(blank)" for c in seen)) or "none"


def build_report(
    matched: pd.DataFrame,
    findings: dict[str, pd.DataFrame],
    rejected: pd.DataFrame,
    stats: dict[str, SourceStats],
    cfg: Config,
) -> str:
    recorded = int(matched["ops_amount_cents"].sum())
    settled = int(matched["settlement_total_cents"].sum())
    gross = int(matched["amount_difference_cents"].abs().sum())
    fired = {name: df for name, df in findings.items() if not df.empty}
    flagged_refs = int(matched["recon_status"].isin(FINDING_STATUSES).sum())

    integrity = pd.DataFrame(
        [
            {
                "source": s.source,
                "rows read": s.rows_read,
                "processed": s.rows_processed,
                "rejected": s.rows_rejected,
                "rejected amount": _fmt_money(s.amount_rejected_cents),
                "unparseable amounts": s.unparseable_amounts,
            }
            for s in stats.values()
        ]
    )

    by_status = (
        matched.groupby("recon_status")
        .agg(
            references=("transaction_ref", "size"),
            recorded_cents=("ops_amount_cents", "sum"),
            settled_cents=("settlement_total_cents", "sum"),
        )
        .reindex([s for s in STATUS_MEANING if s in set(matched["recon_status"])])
        .rename_axis("status")
        .reset_index()
    )
    by_status.insert(1, "meaning", by_status["status"].map(STATUS_MEANING))

    lines = [
        "# Reconciliation Executive Report",
        "",
        f"_Engine: {cfg.engine} · tolerance {cfg.amount_tolerance} · duplicate-charge window "
        f"{cfg.duplicate_window_minutes} min · reconciliation-engine {__version__}_",
        "",
        "## Input integrity",
        "",
        integrity.to_markdown(index=False, disable_numparse=True),
        "",
        "Conservation checks passed: per source, rows read = processed + rejected and the "
        "parseable amount read = processed + rejected amount; the matched table carries every "
        "processed row and cent.",
        "",
        "## Health at a glance",
        "",
        f"- **References:** {len(matched)} ({int(matched['has_ops'].sum())} in ops, "
        f"{int(matched['has_billing'].sum())} in billing)",
        f"- **Recorded total (ops):** {_fmt_money(recorded)}",
        f"- **Settled total (billing):** {_fmt_money(settled)}",
        f"- **Net difference (settled − recorded):** {_fmt_money(settled - recorded)}",
        f"- **Gross difference (sum of |settled − recorded| per reference):** {_fmt_money(gross)}",
        f"- **Currencies in input:** {_currencies(matched)}",
        f"- **References with a reconciliation finding:** {flagged_refs} · **rules fired:** "
        f"{len(fired)} · **flagged rows:** {sum(len(df) for df in fired.values())}",
        "",
        "### Status per reference",
        "",
        _markdown(by_status),
        "",
        "## Findings",
        "",
    ]

    if not fired:
        lines.append("No anomalies detected. Sources reconcile within tolerance.")
    for name, df in fired.items():
        title = name.replace("_", " ").title()
        summary = (ANOMALY_RULES[name].__doc__ or "").strip().splitlines()[0]
        lines += [f"### {title} ({len(df)})", "", summary, "", _markdown(df), ""]

    if not rejected.empty:
        shown = rejected.head(MAX_REJECTED_IN_REPORT)
        lines += [
            "",
            f"## Rejected rows ({len(rejected)})",
            "",
            "Rows that could not be reconciled as read. They are excluded from the totals "
            "above and listed in full in `rejected_rows.csv`.",
            "",
            _markdown(shown),
        ]
        if len(rejected) > len(shown):
            lines.append(f"\n_First {len(shown)} of {len(rejected)} shown._")

    lines += ["", "---", f"_Generated by reconciliation-engine {__version__}_", ""]
    return "\n".join(lines)


def _write_csv(df: pd.DataFrame, path: Path) -> None:
    to_display(df).to_csv(path, index=False, lineterminator="\n")


def export_findings_csv(findings: dict[str, pd.DataFrame], cfg: Config) -> list[Path]:
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for name, df in findings.items():
        path = cfg.output_dir / f"anomalies_{name}.csv"
        _write_csv(df, path)
        paths.append(path)
    return paths


def export_rejected_csv(rejected: pd.DataFrame, cfg: Config) -> Path:
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    path = cfg.output_dir / "rejected_rows.csv"
    _write_csv(rejected, path)
    return path


def export_report(
    matched: pd.DataFrame,
    findings: dict[str, pd.DataFrame],
    rejected: pd.DataFrame,
    stats: dict[str, SourceStats],
    cfg: Config,
) -> Path:
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    path = cfg.output_dir / "reconciliation_report.md"
    path.write_text(
        build_report(matched, findings, rejected, stats, cfg), encoding="utf-8", newline="\n"
    )
    return path
