"""SQLite decision log (stdlib sqlite3) and the SQL metrics built on it.

Every decision the desk returns is written here, so it can be audited later:
which source decided (llm/fallback), with which model and prompt, what was
proposed, which rules fired and whether they overrode the proposal.

One short-lived connection per call keeps it safe under ThreadingHTTPServer.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at        TEXT    NOT NULL,                 -- UTC, ISO-8601
    ticket_ref        TEXT,                             -- optional caller id (e.g. TK-1001)
    ticket_sha256     TEXT    NOT NULL,
    ticket_text       TEXT    NOT NULL,
    ticket_amount     REAL    NOT NULL,
    source            TEXT    NOT NULL CHECK (source IN ('llm', 'fallback')),
    model             TEXT,                             -- NULL when the fallback decided
    prompt_version    TEXT    NOT NULL,
    prompt_sha256     TEXT    NOT NULL,
    proposed_category TEXT    NOT NULL,
    proposed_severity TEXT    NOT NULL,
    category          TEXT    NOT NULL,
    severity          TEXT    NOT NULL,
    confidence        REAL    NOT NULL,
    refund_request    INTEGER NOT NULL,
    exposure_mxn      REAL    NOT NULL,
    action            TEXT    NOT NULL,
    escalated         INTEGER NOT NULL,
    rules_override    INTEGER NOT NULL,
    rules_applied     TEXT    NOT NULL,                 -- JSON array of rule ids
    latency_ms        INTEGER NOT NULL,
    fallback_note     TEXT,
    raw_output        TEXT                              -- model answer as received
);
CREATE INDEX IF NOT EXISTS idx_decisions_created_at ON decisions (created_at);
"""

COLUMNS = (
    "created_at", "ticket_ref", "ticket_sha256", "ticket_text", "ticket_amount", "source",
    "model", "prompt_version", "prompt_sha256", "proposed_category", "proposed_severity",
    "category", "severity", "confidence", "refund_request", "exposure_mxn", "action",
    "escalated", "rules_override", "rules_applied", "latency_ms", "fallback_note", "raw_output",
)  # fmt: skip

# The metrics are plain SQL so they can be run as-is from any SQLite client.
METRICS_SQL = {
    "totals": """
        SELECT COUNT(*)                                            AS decisions,
               ROUND(AVG(escalated), 4)                            AS escalation_rate,
               ROUND(AVG(rules_override), 4)                       AS rules_override_rate,
               ROUND(AVG(CASE WHEN source = 'fallback' THEN 1.0 ELSE 0.0 END), 4)
                                                                   AS fallback_rate
        FROM decisions
    """,
    "by_source": """
        SELECT source,
               COUNT(*)                         AS decisions,
               ROUND(AVG(escalated), 4)         AS escalation_rate,
               ROUND(AVG(rules_override), 4)    AS rules_override_rate,
               CAST(AVG(latency_ms) AS INTEGER) AS avg_latency_ms
        FROM decisions
        GROUP BY source
        ORDER BY decisions DESC, source
    """,
    "by_action": """
        SELECT action, COUNT(*) AS decisions
        FROM decisions
        GROUP BY action
        ORDER BY decisions DESC, action
    """,
    "rules_fired": """
        SELECT rule.value AS rule, COUNT(*) AS decisions
        FROM decisions, json_each(decisions.rules_applied) AS rule
        GROUP BY rule.value
        ORDER BY decisions DESC, rule
    """,
    "category_changed_by_rules": """
        SELECT COUNT(*) AS decisions
        FROM decisions
        WHERE category <> proposed_category
    """,
}


class DecisionStore:
    """Append-only decision log in a SQLite file."""

    def __init__(self, path: str) -> None:
        if not path or path == ":memory:":
            raise ValueError("DecisionStore needs a file path (':memory:' is not shared)")
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as con, con:
            con.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=5.0)
        con.row_factory = sqlite3.Row
        return con

    def record(self, row: dict[str, Any]) -> int:
        """Insert one decision; returns its id."""
        values = dict(row)
        values.setdefault("created_at", datetime.now(timezone.utc).isoformat(timespec="seconds"))
        values["rules_applied"] = json.dumps(list(values.get("rules_applied", [])))
        for flag in ("refund_request", "escalated", "rules_override"):
            values[flag] = int(bool(values.get(flag)))
        placeholders = ", ".join("?" for _ in COLUMNS)
        sql = f"INSERT INTO decisions ({', '.join(COLUMNS)}) VALUES ({placeholders})"
        with closing(self._connect()) as con, con:
            cursor = con.execute(sql, [values.get(column) for column in COLUMNS])
            return int(cursor.lastrowid or 0)

    def get(self, decision_id: int) -> dict[str, Any] | None:
        with closing(self._connect()) as con:
            found = con.execute("SELECT * FROM decisions WHERE id = ?", (decision_id,)).fetchone()
        return dict(found) if found else None

    def metrics(self) -> dict[str, Any]:
        """Run every query in METRICS_SQL; one-row queries return a dict, others a list."""
        out: dict[str, Any] = {}
        with closing(self._connect()) as con:
            for name, sql in METRICS_SQL.items():
                rows = [dict(r) for r in con.execute(sql).fetchall()]
                out[name] = rows[0] if name in ("totals", "category_changed_by_rules") else rows
        out["category_changed_by_rules"] = out["category_changed_by_rules"]["decisions"]
        return out
