"""Reconciliation Engine: cross-match two financial data sources and detect anomalies."""

__version__ = "1.0.0"

from .config import Config
from .pipeline import run_reconciliation

__all__ = ["Config", "run_reconciliation", "__version__"]
