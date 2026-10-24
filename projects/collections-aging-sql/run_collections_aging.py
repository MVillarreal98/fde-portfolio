"""Runs the demo end to end on the committed synthetic data (data/ -> output/)."""

import logging
from pathlib import Path

from aging_sql.engine import run_pipeline

HERE = Path(__file__).resolve().parent


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    out_dir = HERE / "output"
    result = run_pipeline(
        invoices_path=HERE / "data" / "invoices.csv",
        payments_path=HERE / "data" / "payments.csv",
        out_dir=out_dir,
    )
    print(f"as of {result.as_of}: wrote {len(result.files) + 1} output files to {out_dir}")


if __name__ == "__main__":
    main()
