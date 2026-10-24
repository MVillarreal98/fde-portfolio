"""Structured logging: one JSON object per line on stderr (container-friendly).

Usage: `log.info("triage_decision", extra={"fields": {...}})`. The message is the
event name; `fields` become top-level keys. Customer text is never logged — only
hashes and ids that point into the SQLite decision log.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

LOGGER_NAME = "support_desk"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            entry.update(fields)
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO", stream=None) -> None:
    """Route every `support_desk.*` logger to one JSON handler (idempotent)."""
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger(LOGGER_NAME)
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    root.propagate = False
