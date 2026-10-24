"""One-command demo launcher; the same CLI is installed as the `reconcile` script.

Without arguments it reconciles the bundled synthetic data in data/ and writes
to output/ next to this file, from any working directory. Any CLI option can
be added and overrides the demo defaults (argparse keeps the last value).
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "src"))

from reconciliation.cli import main  # noqa: E402

DEMO_DEFAULTS = [
    "--ops",
    str(HERE / "data" / "ops_transactions.csv"),
    "--billing",
    str(HERE / "data" / "billing_statements.csv"),
    "--out",
    str(HERE / "output"),
]

if __name__ == "__main__":
    raise SystemExit(main(DEMO_DEFAULTS + sys.argv[1:]))
