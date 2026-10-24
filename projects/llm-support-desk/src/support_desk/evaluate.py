"""Offline evaluation against the labeled synthetic tickets.

Two questions, measured separately:
1. Classification quality: does the final category match the label?
2. Safety: does every ticket that policy says must reach a human end up
   escalated, whatever the model answered?

The labels and the keyword fallback were written by the same author, so the
fallback's agreement on this file is optimistic, not a generalization estimate.
"""

from __future__ import annotations

import csv
import statistics
from pathlib import Path

from .llm_client import LLMUnavailable
from .rules import ESCALATE
from .service import TriageService

DEFAULT_CSV = "data/sample_tickets.csv"


class _NoLLM:
    """Forces the deterministic fallback for every ticket."""

    def chat(self, messages):
        raise LLMUnavailable("eval: fallback mode")


def load_labeled(path: str | Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    required = {"ticket_id", "customer_text", "amount", "expected_category", "must_escalate"}
    missing = required - set(rows[0] if rows else {})
    if missing:
        raise ValueError(f"{path}: missing columns {sorted(missing)}")
    return rows


def evaluate(service: TriageService, rows: list[dict]) -> dict:
    """Triage every row and compare against its labels."""
    results = []
    for row in rows:
        decision = service.triage(
            row["customer_text"], float(row["amount"]), row.get("history", ""), row["ticket_id"]
        )
        results.append(
            {
                "ticket_id": row["ticket_id"],
                "expected_category": row["expected_category"],
                "must_escalate": row["must_escalate"].strip().lower() == "yes",
                "category": decision["category"],
                "source": decision["source"],
                "escalated": decision["escalated"],
                "action": decision["action"],
                "rules_applied": decision["rules_applied"],
                "rules_override": decision["rules_override"],
                "latency_ms": decision["latency_ms"],
            }
        )

    llm_rows = [r for r in results if r["source"] == "llm"]
    must = [r for r in results if r["must_escalate"]]
    optional = [r for r in results if not r["must_escalate"]]
    return {
        "tickets": len(results),
        "sources": {s: sum(r["source"] == s for r in results) for s in ("llm", "fallback")},
        "category_agreement": sum(r["category"] == r["expected_category"] for r in results),
        "llm_answers": len(llm_rows),
        "llm_category_agreement": sum(r["category"] == r["expected_category"] for r in llm_rows),
        "must_escalate": len(must),
        "must_escalate_escalated": sum(r["escalated"] for r in must),
        "missed_escalations": [r["ticket_id"] for r in must if not r["escalated"]],
        "optional_escalate": len(optional),
        "optional_escalated": sum(r["escalated"] for r in optional),
        "first_line_actions": sum(r["action"] != ESCALATE for r in results),
        "rules_overrides": sum(r["rules_override"] for r in results),
        "median_latency_ms": int(statistics.median(r["latency_ms"] for r in results))
        if results
        else 0,
        "misclassified": [
            {k: r[k] for k in ("ticket_id", "expected_category", "category", "source")}
            for r in results
            if r["category"] != r["expected_category"]
        ],
    }


def _pct(part: int, whole: int) -> str:
    return f"{part}/{whole} ({part / whole:.0%})" if whole else "0/0"


def format_report(mode: str, model: str | None, csv_path: str, m: dict) -> str:
    lines = [
        f"mode={mode} model={model or '-'} tickets={m['tickets']} data={csv_path} (synthetic)",
        f"  category agreement (final decision): {_pct(m['category_agreement'], m['tickets'])}",
        f"  decided by: llm={m['sources']['llm']} fallback={m['sources']['fallback']}",
    ]
    if mode == "llm":
        lines.append(
            f"  LLM answers that passed the schema: {_pct(m['llm_answers'], m['tickets'])}; "
            f"category agreement on those: {_pct(m['llm_category_agreement'], m['llm_answers'])}"
        )
    lines += [
        f"  must-escalate tickets escalated: "
        f"{_pct(m['must_escalate_escalated'], m['must_escalate'])}; "
        f"missed: {', '.join(m['missed_escalations']) or 'none'}",
        f"  escalated without a policy need: "
        f"{_pct(m['optional_escalated'], m['optional_escalate'])}",
        f"  rules overrode the proposal: {m['rules_overrides']}; "
        f"first-line actions: {m['first_line_actions']}; "
        f"median latency: {m['median_latency_ms']} ms",
    ]
    for miss in m["misclassified"]:
        lines.append(
            f"    miss {miss['ticket_id']}: expected {miss['expected_category']}, "
            f"got {miss['category']} ({miss['source']})"
        )
    return "\n".join(lines)


def fallback_service(cfg) -> TriageService:
    return TriageService(cfg, llm=_NoLLM())
