"""Collections aging cockpit — DuckDB SQL pipeline for payment collections."""

from aging_sql._version import __version__
from aging_sql.engine import (
    AgingDataError,
    ConservationIntegrityError,
    Finding,
    RunResult,
    run_pipeline,
)

__all__ = [
    "AgingDataError",
    "ConservationIntegrityError",
    "Finding",
    "RunResult",
    "__version__",
    "run_pipeline",
]
