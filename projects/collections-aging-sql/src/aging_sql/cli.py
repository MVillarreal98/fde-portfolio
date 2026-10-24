"""Command-line entry point for the collections aging pipeline."""

from __future__ import annotations

import argparse
import logging
from datetime import date

from aging_sql._version import __version__
from aging_sql.engine import AS_OF_DEFAULT, AgingDataError, run_pipeline

logger = logging.getLogger("collections-aging")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="collections-aging",
        description=(
            "Ages every open invoice, assigns the dunning stage per policy and"
            " lists duplicate-payment candidates, findings and rejected rows."
            " All business logic runs as DuckDB SQL; this CLI only stages the"
            " CSVs and writes the outputs."
        ),
    )
    parser.add_argument("--invoices", required=True, help="path to invoices.csv")
    parser.add_argument("--payments", required=True, help="path to payments.csv")
    parser.add_argument(
        "--out",
        required=True,
        help="directory for the CSV reports and collections_report.md (created if missing)",
    )
    parser.add_argument(
        "--as-of",
        default=AS_OF_DEFAULT,
        help="aging reference date, ISO YYYY-MM-DD (default: " + AS_OF_DEFAULT + ")",
    )
    parser.add_argument(
        "--fail-on-findings",
        action="store_true",
        help="exit with code 2 when any finding was raised (for schedulers)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="log verbosity (default: INFO)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"collections-aging {__version__}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=args.log_level, format="%(levelname)s %(name)s: %(message)s")
    try:
        date.fromisoformat(args.as_of)
    except ValueError:
        # 4 = we never ran: a bad flag is not a pipeline failure (1) and not
        # "findings were raised" (2). Codes: 0 clean, 1 pipeline failure,
        # 2 findings under --fail-on-findings, 4 bad flag value.
        parser.exit(
            4,
            "collections-aging: error: "
            f"--as-of must be an ISO date (YYYY-MM-DD), got: {args.as_of}\n",
        )

    try:
        result = run_pipeline(
            invoices_path=args.invoices,
            payments_path=args.payments,
            out_dir=args.out,
            as_of=args.as_of,
        )
    except AgingDataError as exc:
        logger.error("%s", exc)
        return 1

    logger.info(
        "totals: invoiced %d | applied %d | unapplied %d | outstanding %d (cents)",
        result.invoiced_cents,
        result.applied_cents,
        result.unapplied_cents,
        result.outstanding_cents,
    )
    logger.info("findings: %d", len(result.findings))
    if args.fail_on_findings and result.findings:
        return 2
    return 0
