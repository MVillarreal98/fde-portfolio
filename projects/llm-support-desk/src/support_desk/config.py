"""Runtime configuration. Every external dependency (host, model, ports,
thresholds, storage) is env-overridable so ops can retune without code changes.

Values are read when `Config()` is instantiated (never at import time), and an
invalid value fails with a message that names the variable.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Company policy default: first-line agents may close claims up to this amount.
# Above it, the claim goes to a human supervisor (see rules.py).
REFUND_AUTOCAP_MXN = 500.00

LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from None


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        raise ValueError(f"{name} must be a number, got {raw!r}") from None


def _default_db_path() -> str:
    # Outside the repository on purpose: decisions contain customer text.
    return str(Path.home() / ".support-desk" / "decisions.db")


@dataclass
class Config:
    # Ollama local REST endpoint (default from `ollama serve`).
    ollama_host: str = field(default_factory=lambda: _env("OLLAMA_HOST", "http://localhost:11434"))
    model: str = field(default_factory=lambda: _env("OLLAMA_MODEL", "llama3.2:1b"))
    # Temperature 0 + fixed seed: the same ticket gets the same answer (reproducible audits).
    temperature: float = field(default_factory=lambda: _env_float("OLLAMA_TEMPERATURE", 0.0))
    seed: int = field(default_factory=lambda: _env_int("OLLAMA_SEED", 42))

    http_host: str = field(default_factory=lambda: _env("SUPPORT_DESK_HOST", "localhost"))
    http_port: int = field(default_factory=lambda: _env_int("SUPPORT_DESK_PORT", 8000))

    # Seconds allowed for one full local-inference decision (CPU inference included).
    llm_timeout_s: float = field(default_factory=lambda: _env_float("SUPPORT_DESK_TIMEOUT_S", 60.0))
    # Background LLM probe: short timeout, cached result. /api/health never waits on it.
    probe_timeout_s: float = field(
        default_factory=lambda: _env_float("SUPPORT_DESK_PROBE_TIMEOUT_S", 2.0)
    )
    probe_interval_s: float = field(
        default_factory=lambda: _env_float("SUPPORT_DESK_PROBE_INTERVAL_S", 15.0)
    )

    # A decision at or below this confidence is escalated, never auto-executed.
    escalation_threshold: float = field(
        default_factory=lambda: _env_float("SUPPORT_DESK_ESCALATION", 0.60)
    )
    # Money at stake above this amount always goes to a human.
    refund_cap_mxn: float = field(
        default_factory=lambda: _env_float("SUPPORT_DESK_REFUND_CAP_MXN", REFUND_AUTOCAP_MXN)
    )

    # Largest accepted POST body; bigger requests get HTTP 413.
    max_body_bytes: int = field(
        default_factory=lambda: _env_int("SUPPORT_DESK_MAX_BODY_BYTES", 16_384)
    )
    # SQLite file for the decision log. Empty string disables persistence.
    db_path: str = field(default_factory=lambda: _env("SUPPORT_DESK_DB", _default_db_path()))
    log_level: str = field(default_factory=lambda: _env("SUPPORT_DESK_LOG_LEVEL", "INFO").upper())

    def __post_init__(self) -> None:
        if not 0.0 <= self.escalation_threshold <= 1.0:
            raise ValueError("SUPPORT_DESK_ESCALATION must be between 0 and 1")
        if self.refund_cap_mxn < 0:
            raise ValueError("SUPPORT_DESK_REFUND_CAP_MXN must be >= 0")
        if self.max_body_bytes <= 0:
            raise ValueError("SUPPORT_DESK_MAX_BODY_BYTES must be > 0")
        if self.log_level not in LOG_LEVELS:
            raise ValueError(f"SUPPORT_DESK_LOG_LEVEL must be one of {', '.join(LOG_LEVELS)}")


TRIAGE_CATEGORIES = [
    "duplicate_charge",
    "payment_not_received",
    "unauthorized_charge",
    "app_issue",
    "amount_discrepancy",
]
