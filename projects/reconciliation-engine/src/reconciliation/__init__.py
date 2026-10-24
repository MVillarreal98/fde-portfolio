"""Reconciliation Engine: cross-match two financial data sources and detect anomalies."""

__version__ = "2.0.0"

from .config import Config
from .pipeline import (
    ReconciliationIntegrityError,
    ReconciliationResult,
    run_reconciliation,
)

__all__ = [
    "Config",
    "ReconciliationIntegrityError",
    "ReconciliationResult",
    "run_reconciliation",
    "__version__",
]
