"""Make `src/` importable for the test suite without installing the package."""

import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


@pytest.fixture(autouse=True)
def _reset_logging():
    """CLI tests configure the JSON handler; undo it so caplog keeps working."""
    yield
    logger = logging.getLogger("support_desk")
    logger.handlers[:] = []
    logger.propagate = True
    logger.setLevel(logging.NOTSET)
