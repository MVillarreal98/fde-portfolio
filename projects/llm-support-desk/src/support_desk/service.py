"""Triage orchestration: LLM first, schema-validated, rules-enforced,
deterministic fallback when the model is down. Never trust-before-validate.

Every decision is logged (structured, no customer text) and, when a store is
configured, persisted to SQLite with the prompt hash and the rules that fired.
"""

from __future__ import annotations

import hashlib
import logging
import math
import sqlite3
import time

from .config import Config
from .health import UNKNOWN, LLMStatusMonitor
from .llm_client import CONNECTED, LLMUnavailable
from .prompts import PROMPT_VERSION, build_messages, prompt_hash
from .rules import fallback_classify, post_validate
from .schema import parse

log = logging.getLogger(__name__)

RAW_OUTPUT_MAX_CHARS = 4000


class TriageService:
    def __init__(self, cfg: Config, llm=None, store=None) -> None:
        self.cfg = cfg
        # Injected client (kept loose for tests); instantiated lazily in prod.
        self._llm = llm
        # Optional DecisionStore; None means decisions are not persisted.
        self.store = store
        self.monitor = LLMStatusMonitor(self._probe_llm, cfg.probe_interval_s)

    @property
    def llm(self):
        if self._llm is None:
            from .llm_client import OllamaClient

            self._llm = OllamaClient(
                self.cfg.ollama_host,
                self.cfg.model,
                self.cfg.llm_timeout_s,
                temperature=self.cfg.temperature,
                seed=self.cfg.seed,
                probe_timeout_s=self.cfg.probe_timeout_s,
            )
        return self._llm

    def _probe_llm(self) -> str:
        status = getattr(self.llm, "status", None)
        return status() if callable(status) else UNKNOWN

    def llm_state(self) -> str:
        """Cached LLM state for /api/health (never blocks on Ollama)."""
        return self.monitor.state()

    def triage(
        self, ticket_text: str, amount: float, history: str = "", ticket_ref: str | None = None
    ) -> dict:
        ticket_text = (ticket_text or "").strip()
        if not ticket_text:
            return {"error": "empty ticket text", "source": "input"}
        try:
            amount = float(amount or 0.0)
        except (TypeError, ValueError):
            return {"error": "amount must be a number", "source": "input"}
        if not math.isfinite(amount) or amount < 0:
            return {"error": "amount must be a finite number >= 0", "source": "input"}

        messages = build_messages(ticket_text, amount, history)
        started = time.perf_counter()
        source, raw = "llm", None
        try:
            raw = self.llm.chat(messages)
            decision = parse(raw)
            self.monitor.mark(CONNECTED)
        except LLMUnavailable as exc:
            decision = fallback_classify(ticket_text, amount)
            decision["fallback_note"] = f"LLM unavailable: {exc}"
            source = "fallback"
            self.monitor.invalidate()
        except ValueError as exc:
            # Model answered but broke the contract: rules keep the desk honest.
            decision = fallback_classify(ticket_text, amount)
            decision["fallback_note"] = f"Invalid model output: {exc}"
            source = "fallback"
        except Exception as exc:  # unexpected client failure must not take the desk down
            log.exception("llm_client_error")
            decision = fallback_classify(ticket_text, amount)
            decision["fallback_note"] = f"LLM client error: {type(exc).__name__}"
            source = "fallback"
            self.monitor.invalidate()
        latency_ms = int((time.perf_counter() - started) * 1000)

        proposed = {"category": decision["category"], "severity": decision["severity"]}
        decision["ticket_amount"] = round(amount, 2)
        decision = post_validate(decision, decision["ticket_amount"], self.cfg, ticket_text)
        decision["source"] = source
        decision["model"] = self.cfg.model if source == "llm" else None
        decision["prompt_version"] = PROMPT_VERSION
        decision["prompt_sha256"] = prompt_hash(messages)
        decision["latency_ms"] = latency_ms
        ticket_sha256 = hashlib.sha256(ticket_text.encode("utf-8")).hexdigest()
        decision["decision_id"] = self._persist(
            decision, proposed, ticket_text, ticket_sha256, ticket_ref, raw
        )

        log.info(
            "triage_decision",
            extra={
                "fields": {
                    "decision_id": decision["decision_id"],
                    "ticket_ref": ticket_ref,
                    "ticket_sha256": ticket_sha256[:16],
                    "source": source,
                    "model": decision["model"],
                    "prompt_version": PROMPT_VERSION,
                    "prompt_sha256": decision["prompt_sha256"][:16],
                    "category": decision["category"],
                    "severity": decision["severity"],
                    "action": decision["action"],
                    "escalated": decision["escalated"],
                    "rules_applied": decision["rules_applied"],
                    "rules_override": decision["rules_override"],
                    "latency_ms": latency_ms,
                }
            },
        )
        return decision

    def _persist(
        self,
        decision: dict,
        proposed: dict,
        ticket_text: str,
        ticket_sha256: str,
        ticket_ref: str | None,
        raw: str | None,
    ) -> int | None:
        if self.store is None:
            return None
        row = {
            "ticket_ref": ticket_ref,
            "ticket_sha256": ticket_sha256,
            "ticket_text": ticket_text,
            "ticket_amount": decision["ticket_amount"],
            "source": decision["source"],
            "model": decision["model"],
            "prompt_version": decision["prompt_version"],
            "prompt_sha256": decision["prompt_sha256"],
            "proposed_category": str(proposed["category"]),
            "proposed_severity": str(proposed["severity"]),
            "category": decision["category"],
            "severity": decision["severity"],
            "confidence": decision["confidence"],
            "refund_request": decision.get("refund_request", False),
            "exposure_mxn": decision["exposure_mxn"],
            "action": decision["action"],
            "escalated": decision["escalated"],
            "rules_override": decision["rules_override"],
            "rules_applied": decision["rules_applied"],
            "latency_ms": decision["latency_ms"],
            "fallback_note": decision.get("fallback_note"),
            "raw_output": raw[:RAW_OUTPUT_MAX_CHARS] if raw is not None else None,
        }
        try:
            return self.store.record(row)
        except sqlite3.Error:
            # The decision is still returned; the failure is loud in the logs.
            log.exception("decision_persist_failed")
            return None
