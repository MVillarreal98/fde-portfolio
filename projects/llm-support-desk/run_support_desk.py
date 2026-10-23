"""Thin launcher retained for one-command demos; the server is also installed
as a console script (`support-desk`) by pyproject.toml."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from support_desk.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
