"""Support Desk Triage Agent: local-LLM claim triage with business rules."""

__version__ = "1.0.0"

from .config import Config
from .service import TriageService

__all__ = ["Config", "TriageService", "__version__"]
