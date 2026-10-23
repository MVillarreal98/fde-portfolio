"""Thin launcher retained for one-command demos; the CLI is also installed
as a console script (`reconcile`) by pyproject.toml."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from reconciliation.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
