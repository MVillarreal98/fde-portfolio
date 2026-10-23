"""Command-line entry point (made an `entry_points` console script in pyproject)."""

from __future__ import annotations

import argparse
from pathlib import Path

from . import Config, run_reconciliation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconcile ops ledger vs billing data.")
    parser.add_argument("--ops", type=Path, default=Path("data/ops_transactions.csv"))
    parser.add_argument("--billing", type=Path, default=Path("data/billing_statements.csv"))
    parser.add_argument("--out", type=Path, default=Path("output"))
    parser.add_argument("--tolerance", type=float, default=0.01)
    args = parser.parse_args(argv)

    cfg = Config(
        ops_path=args.ops,
        billing_path=args.billing,
        output_dir=args.out,
        amount_tolerance=args.tolerance,
    )
    result = run_reconciliation(cfg)
    print(f"[ok] Anomaly files: {', '.join(result.csv_paths) or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
