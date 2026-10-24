"""Cached LLM status, so liveness never depends on Ollama answering in time.

`/api/health` reads `LLMStatusMonitor.state()`, which returns immediately with the
last known value and, when that value is stale, refreshes it on a background
thread. A hung Ollama therefore makes the desk report "degraded", never makes
the container's HEALTHCHECK time out.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable

UNKNOWN = "unknown"

log = logging.getLogger(__name__)


class LLMStatusMonitor:
    def __init__(self, probe: Callable[[], str], interval_s: float) -> None:
        self._probe = probe
        self._interval_s = interval_s
        self._state = UNKNOWN
        self._checked_at: float | None = None
        self._refreshing = False
        self._lock = threading.Lock()

    def state(self) -> str:
        """Last known state; never blocks on the probe."""
        with self._lock:
            stale = (
                self._checked_at is None or time.monotonic() - self._checked_at >= self._interval_s
            )
            if stale and not self._refreshing:
                self._refreshing = True
                threading.Thread(target=self.refresh, name="llm-probe", daemon=True).start()
            return self._state

    def refresh(self) -> str:
        """Probe synchronously (startup, background thread) and cache the result."""
        try:
            state = self._probe()
        except Exception:  # a probe must never take the service down
            log.exception("llm_probe_failed")
            state = "unreachable"
        with self._lock:
            previous, self._state = self._state, state
            self._checked_at = time.monotonic()
            self._refreshing = False
        if state != previous:
            log.info("llm_state_changed", extra={"fields": {"from": previous, "to": state}})
        return state

    def mark(self, state: str) -> None:
        """Record what real traffic just observed (cheaper than probing)."""
        with self._lock:
            self._state = state
            self._checked_at = time.monotonic()

    def invalidate(self) -> None:
        """Force the next `state()` call to re-probe in the background."""
        with self._lock:
            self._checked_at = None
