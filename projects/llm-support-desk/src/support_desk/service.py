"""Triage orchestration: LLM first, schema-validated, rules-enforced,
deterministic fallback when the model is down. Never trust-before-validate."""

from __future__ import annotations

from .config import Config
from .llm_client import LLMUnavailable
from .prompts import build_messages
from .schema import parse
from .rules import post_validate, fallback_classify


class TriageService:
    def __init__(self, cfg: Config, llm=None) -> None:
        self.cfg = cfg
        # Injected client (kept loose for tests); instantiated lazily in prod.
        self._llm = llm

    @property
    def llm(self):
        if self._llm is None:
            from .llm_client import OllamaClient
            self._llm = OllamaClient(self.cfg.ollama_host, self.cfg.model, self.cfg.llm_timeout_s)
        return self._llm

    def triage(self, ticket_text: str, amount: float, history: str = "") -> dict:
        ticket_text = (ticket_text or "").strip()
        if not ticket_text:
            return {"error": "empty ticket text", "source": "input"}

        source = "llm"
        try:
            raw = self.llm.chat(build_messages(ticket_text, amount, history))
            decision = parse(raw)
        except LLMUnavailable as exc:
            decision = fallback_classify(ticket_text, amount)
            decision["fallback_note"] = f"LLM unavailable: {exc}"
            source = "fallback"
        except ValueError as exc:
            # Model answered but broke the contract: rules keep the desk honest.
            decision = fallback_classify(ticket_text, amount)
            decision["fallback_note"] = f"Invalid model output: {exc}"
            source = "fallback"

        decision["ticket_amount"] = round(float(amount or 0.0), 2)
        decision = post_validate(decision, decision["ticket_amount"], self.cfg)
        decision["source"] = source
        return decision
