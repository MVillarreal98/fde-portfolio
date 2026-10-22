"""CLI entrypoint for the Reconciliation Engine.

Usage:
    python run_reconciliation.py [--ops DATA/OPS.CSV] [--billing DATA/BILLING.CSV]
                                 [--out OUTPUT_DIR] [--tolerance 0.01]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from reconciliation import Config, run_reconciliation  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile ops ledger vs billing data.")
    parser.add_argument("--ops", type=Path, default=Path("data/ops_transactions.csv"))
    parser.add_argument("--billing", type=Path, default=Path("data/billing_statements.csv"))
    parser.add_argument("--out", type=Path, default=Path("output"))
    parser.add_argument("--tolerance", type=float, default=0.01)
    args = parser.parse_args()

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
