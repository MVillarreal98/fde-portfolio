"""Command-line entry point (installed as the ``reconcile`` console script).

Exit codes are meant for schedulers and CI:
  0  run completed (no findings, or findings without --fail-on-findings)
  1  run failed: unreadable input, schema error, invalid option, broken invariant
  2  run completed with findings or rejected rows and --fail-on-findings was set
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import NoReturn

from . import __version__
from .config import ENGINES, Config, parse_tolerance
from .pipeline import ReconciliationIntegrityError, run_reconciliation

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_FINDINGS = 2

log = logging.getLogger("reconciliation.cli")


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        # argparse exits 2 on usage errors; 2 is reserved for "findings" here.
        self.print_usage(sys.stderr)
        self.exit(EXIT_ERROR, f"{self.prog}: error: {message}\n")


def _tolerance(text: str) -> str:
    try:
        parse_tolerance(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None
    return text


def _non_negative_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected an integer, got {text!r}") from None
    if value < 0:
        raise argparse.ArgumentTypeError(f"must be >= 0, got {value}")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="reconcile",
        description="Reconcile an operational ledger against a billing/settlement export and "
        "write an executive report, one CSV per rule and rejected_rows.csv.",
        epilog="exit codes: 0 completed, 1 error, 2 findings or rejected rows "
        "(only with --fail-on-findings)",
    )
    parser.add_argument(
        "--ops",
        type=Path,
        required=True,
        help="ops ledger CSV (system of record), one row per capture",
    )
    parser.add_argument(
        "--billing", type=Path, required=True, help="billing/settlement CSV from the processor"
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("output"),
        help="output directory, created if missing (default: ./output)",
    )
    parser.add_argument(
        "--engine",
        choices=ENGINES,
        default="pandas",
        help="pandas (default) or sql (same rules in DuckDB SQL)",
    )
    parser.add_argument(
        "--tolerance",
        type=_tolerance,
        default="0.01",
        help="largest absolute difference treated as noise, in currency units; "
        "whole cents, >= 0 (default: 0.01)",
    )
    parser.add_argument(
        "--duplicate-window-minutes",
        type=_non_negative_int,
        default=10,
        help="max minutes between captures grouped as a possible duplicate charge (default: 10)",
    )
    parser.add_argument(
        "--fail-on-findings",
        action="store_true",
        help="exit with code 2 when any rule fires or any row is rejected",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="logging verbosity on stderr (default: INFO)",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=args.log_level, format="%(levelname)s %(name)s: %(message)s")
    try:
        cfg = Config(
            ops_path=args.ops,
            billing_path=args.billing,
            output_dir=args.out,
            amount_tolerance=args.tolerance,
            duplicate_window_minutes=args.duplicate_window_minutes,
            engine=args.engine,
        )
        result = run_reconciliation(cfg)
    except (OSError, ValueError, ReconciliationIntegrityError) as exc:
        # Data and environment problems get one clear line, not a traceback.
        log.error("%s: %s", type(exc).__name__, exc)
        return EXIT_ERROR
    if args.fail_on_findings and result.needs_attention:
        log.warning("Findings or rejected rows present: exiting with code %d", EXIT_FINDINGS)
        return EXIT_FINDINGS
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
