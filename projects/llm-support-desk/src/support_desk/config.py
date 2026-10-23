"""Runtime configuration. Every external dependency (host, model, ports,
thresholds) env-overridable so ops can retune without code changes."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass
class Config:
    # Ollama local REST endpoint (default from `ollama serve`).
    ollama_host: str = field(default_factory=lambda: _env("OLLAMA_HOST", "http://localhost:11434"))
    model: str = field(default_factory=lambda: _env("OLLAMA_MODEL", "llama3.2"))

    http_host: str = field(default_factory=lambda: _env("SUPPORT_DESK_HOST", "localhost"))
    http_port: int = int(_env("SUPPORT_DESK_PORT", "8000"))

    # Seconds allowed for a full local-inference decision; keeps triage snappy.
    llm_timeout_s: int = int(_env("SUPPORT_DESK_TIMEOUT_S", "90"))

    # A decision at or below this confidence is escalated, never auto-executed.
    escalation_threshold: float = float(_env("SUPPORT_DESK_ESCALATION", "0.60"))


TRIAGE_CATEGORIES = [
    "duplicate_charge",
    "payment_not_received",
    "unauthorized_charge",
    "app_issue",
    "amount_discrepancy",
]
