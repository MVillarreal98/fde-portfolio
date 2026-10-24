"""The DuckDB pipeline: stage the inputs, check conservation, write artifacts.

The Python side is deliberately thin. Every business rule lives in
`sql/*.sql`; this package only sets up the session, runs the files in order
and turns the results into deterministic CSV/Markdown files.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from importlib import resources
from pathlib import Path

import duckdb

from aging_sql._version import __version__
from aging_sql.outputs import cents_to_decimal_str, write_rows_csv

logger = logging.getLogger(__name__)

AS_OF_DEFAULT = "2026-09-30"

CSV_OUTPUTS: tuple[tuple[str, str], ...] = (
    ("aging_buckets.csv", "aging_buckets.sql"),
    ("dunning_states.csv", "dunning_states.sql"),
    ("duplicate_payment_candidates.csv", "duplicate_payment_candidates.sql"),
    ("monthly_collections.csv", "monthly_collections.sql"),
    ("findings.csv", "findings.sql"),
    ("rejected_rows.csv", "rejected_rows.sql"),
)
REPORT_FILENAME = "collections_report.md"
OUTPUT_FILES: tuple[str, ...] = tuple(name for name, _sql in CSV_OUTPUTS) + (REPORT_FILENAME,)

FINDING_CODES = ("orphan_payment", "overpayment")


class AgingDataError(RuntimeError):
    """Unreadable inputs, wrong columns or a breakdown at staging time (exit 1)."""


class ConservationIntegrityError(AgingDataError):
    """The money identity does not hold after staging; results would lie (exit 1)."""


@dataclass(frozen=True)
class Finding:
    code: str
    reference: str
    detail: str


@dataclass
class RunResult:
    as_of: str
    invoices_raw: int = 0
    invoices_valid: int = 0
    invoices_rejected: int = 0
    payments_raw: int = 0
    payments_valid: int = 0
    payments_rejected: int = 0
    invoiced_cents: int = 0
    applied_cents: int = 0
    unapplied_cents: int = 0
    outstanding_cents: int = 0
    findings: list[Finding] = field(default_factory=list)
    files: dict[str, int] = field(default_factory=dict)


def _sql_text(name: str) -> str:
    return (resources.files("aging_sql") / "sql" / name).read_text(encoding="utf-8")


def _csv_literal(path: Path | str) -> str:
    """Escapes a path for use inside the single-quoted placeholder in staging.sql."""
    return str(path).replace("'", "''")


def _run_sql(con: duckdb.DuckDBPyConnection, statement: str) -> tuple[list[str], list[tuple]]:
    result = con.execute(statement)
    columns = [d[0] for d in result.description or []]
    return columns, result.fetchall()


def _check_conservation(con: duckdb.DuckDBPyConnection, result: RunResult) -> None:
    counts = con.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM raw_invoices),
            (SELECT COUNT(*) FROM t_invoices),
            (SELECT COUNT(*) FROM rejected_invoice_rows),
            (SELECT COUNT(*) FROM raw_payments),
            (SELECT COUNT(*) FROM t_payments),
            (SELECT COUNT(*) FROM rejected_payment_rows)
        """
    ).fetchone()
    assert counts is not None
    (
        result.invoices_raw,
        result.invoices_valid,
        result.invoices_rejected,
        result.payments_raw,
        result.payments_valid,
        result.payments_rejected,
    ) = counts
    if result.invoices_raw != result.invoices_valid + result.invoices_rejected:
        raise ConservationIntegrityError(
            f"invoices: raw rows ({result.invoices_raw}) != valid"
            f" ({result.invoices_valid}) + rejected ({result.invoices_rejected})"
        )
    if result.payments_raw != result.payments_valid + result.payments_rejected:
        raise ConservationIntegrityError(
            f"payments: raw rows ({result.payments_raw}) != valid"
            f" ({result.payments_valid}) + rejected ({result.payments_rejected})"
        )

    # Uniqueness ids: the staging dedupe pass makes this hold by construction,
    # but the check stays so a future SQL change cannot reintroduce a repeated
    # id (which inflates invoiced/applied money silently).
    ids = con.execute(
        """
        SELECT
            COUNT(*) - COUNT(DISTINCT invoice_id),
            (SELECT COUNT(*) - COUNT(DISTINCT payment_id) FROM t_payments)
        FROM t_invoices
        """
    ).fetchone()
    assert ids is not None
    if ids[0] or ids[1]:
        raise ConservationIntegrityError(
            f"duplicate ids in the clean pool: {ids[0]} repeated invoice_id,"
            f" {ids[1]} repeated payment_id"
        )

    money = con.execute(
        """
        WITH applied AS (
            SELECT
                i.invoice_id,
                i.amount_cents,
                COALESCE(SUM(a.applied_cents), 0) AS applied_cents
            FROM t_invoices i
            LEFT JOIN t_applied a USING (invoice_id)
            GROUP BY i.invoice_id, i.amount_cents
        )
        SELECT
            COALESCE(SUM(amount_cents), 0),
            COALESCE(SUM(applied_cents), 0),
            COALESCE(SUM(GREATEST(amount_cents - applied_cents, 0)), 0)
        FROM applied
        """
    ).fetchone()
    assert money is not None
    invoiced, applied, outstanding = money
    if invoiced != applied + outstanding:
        raise ConservationIntegrityError(
            f"invoiced cents ({invoiced}) != applied ({applied}) + outstanding ({outstanding})"
        )
    result.invoiced_cents = invoiced
    result.applied_cents = applied
    result.outstanding_cents = outstanding

    unapplied = con.execute(
        "SELECT COALESCE(SUM(pay_amt - applied_cents), 0) FROM t_applied"
    ).fetchone()
    assert unapplied is not None
    result.unapplied_cents = int(unapplied[0])


def _collect_findings(con: duckdb.DuckDBPyConnection, result: RunResult) -> None:
    columns, rows = _run_sql(con, _sql_text("findings.sql"))
    idx = {name: position for position, name in enumerate(columns)}
    result.findings = [
        Finding(
            code=str(row[idx["code"]]),
            reference=str(row[idx["reference"]]),
            detail=str(row[idx["detail"]]),
        )
        for row in rows
    ]


def run_pipeline(
    invoices_path: Path | str,
    payments_path: Path | str,
    out_dir: Path | str,
    as_of: str = AS_OF_DEFAULT,
) -> RunResult:
    """Stages both CSVs, checks conservation and writes every output file."""
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    try:
        validated = date.fromisoformat(as_of).isoformat()  # validated and normalized
    except ValueError as exc:
        raise AgingDataError(f"as_of must be an ISO date (YYYY-MM-DD), got: {as_of!r}") from exc

    result = RunResult(as_of=validated)
    con = duckdb.connect(database=":memory:")
    try:
        con.execute(f"SET VARIABLE as_of = DATE '{validated}'")
        staging = (
            _sql_text("staging.sql")
            .replace("__INVOICES_PATH__", _csv_literal(invoices_path))
            .replace("__PAYMENTS_PATH__", _csv_literal(payments_path))
        )
        try:
            con.execute(staging)
        except duckdb.Error as exc:
            raise AgingDataError(f"could not stage the input files: {exc}") from exc

        _check_conservation(con, result)
        _collect_findings(con, result)

        for filename, sql_name in CSV_OUTPUTS:
            try:
                columns, rows = _run_sql(con, _sql_text(sql_name))
            except duckdb.Error as exc:
                raise AgingDataError(f"{sql_name} failed: {exc}") from exc
            try:
                result.files[filename] = write_rows_csv(columns, rows, out_path / filename)
            except OSError as exc:
                # A locked file (programs/OneDrive) or an unreachable out_dir
                # must keep the same failure contract: the run fails with
                # AgingDataError, not with a raw traceback.
                raise AgingDataError(f"could not write output: {exc}") from exc
            logger.info("wrote %s (%d rows)", filename, result.files[filename])

        report_path = out_path / REPORT_FILENAME
        try:
            # write_bytes, not write_text: text mode translates \n into
            # platform line endings, which would break the byte-for-byte
            # golden comparison of collections_report.md on Windows.
            report_path.write_bytes(_build_report(result).encode("utf-8"))
        except OSError as exc:
            raise AgingDataError(f"could not write output: {exc}") from exc
        logger.info("wrote %s", REPORT_FILENAME)
    finally:
        con.close()
    return result


def _build_report(result: RunResult) -> str:
    # A code missing from FINDING_CODES is counted and rendered with its own
    # code instead of crashing after the CSVs were already written.
    findings_by_code: dict[str, int] = {code: 0 for code in FINDING_CODES}
    for finding in result.findings:
        findings_by_code[finding.code] = findings_by_code.get(finding.code, 0) + 1

    lines = [
        "# Collections aging report",
        "",
        "Synthetic demo data · as of " + result.as_of + " · currency MXN,",
        "all amounts in integer cents.",
        "",
        "## Input integrity",
        "",
        "| source | raw rows | valid rows | rejected rows |",
        "|---|---:|---:|---:|",
        f"| invoices | {result.invoices_raw} | {result.invoices_valid} |"
        f" {result.invoices_rejected} |",
        f"| payments | {result.payments_raw} | {result.payments_valid} |"
        f" {result.payments_rejected} |",
        "",
        "## Money (integer cents)",
        "",
        "| measure | cents | shown as |",
        "|---|---:|---|",
        f"| invoiced | {result.invoiced_cents:,} | {cents_to_decimal_str(result.invoiced_cents)} |",
        f"| applied to invoices | {result.applied_cents:,} |"
        f" {cents_to_decimal_str(result.applied_cents)} |",
        f"| cash above invoice totals (unapplied) | {result.unapplied_cents:,} |"
        f" {cents_to_decimal_str(result.unapplied_cents)} |",
        f"| outstanding | {result.outstanding_cents:,} |"
        f" {cents_to_decimal_str(result.outstanding_cents)} |",
        "",
        "Conservation check: invoiced = applied + outstanding — passed.",
        "",
        "## Findings (by code)",
        "",
        "| code | count |",
        "|---|---:|",
    ]
    lines += [f"| {code} | {findings_by_code[code]} |" for code in FINDING_CODES]
    # Unknown codes cannot appear today, but a future one must still render
    # with its count rather than disappear from the report.
    unknown = [c for c in findings_by_code if c not in FINDING_CODES]
    lines += [f"| {code} (unexpected) | {findings_by_code[code]} |" for code in unknown]
    lines += [
        "",
        "All money figures are built only from rows that passed staging; every",
        "unusable input row is listed in rejected_rows.csv with a reason.",
        "",
        f"generated by collections-aging {__version__}",
    ]
    return "\n".join(lines) + "\n"
