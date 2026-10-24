"""Ollama REST client over urllib.

Deliberately dependency-free: fintech environments often cannot add packages to
the workstation image; urllib keeps the same behavior everywhere.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

# Probe outcomes reported by `OllamaClient.status()` and surfaced on /api/health.
CONNECTED = "connected"
MODEL_MISSING = "model_missing"
UNREACHABLE = "unreachable"


class LLMUnavailable(Exception):
    """Raised when the local inference endpoint is down, slow or wrong."""


class OllamaClient:
    """Thin wrapper around `POST {host}/api/chat` with `format: "json"`.

    Forcing JSON at the protocol level (not just politely asking in the prompt)
    is what makes the downstream schema contract trustworthy.
    """

    def __init__(
        self,
        host: str,
        model: str,
        timeout_s: float = 60,
        *,
        temperature: float = 0.0,
        seed: int = 42,
        probe_timeout_s: float = 2.0,
    ) -> None:
        self.host = host.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s
        self.temperature = temperature
        self.seed = seed
        self.probe_timeout_s = probe_timeout_s

    def chat(self, messages: list[dict]) -> str:
        payload = json.dumps(
            {
                "model": self.model,
                "messages": messages,
                "stream": False,
                "format": "json",  # protocol-level JSON mode
                # Deterministic sampling so a decision can be reproduced later.
                "options": {"temperature": self.temperature, "seed": self.seed},
            }
        ).encode("utf-8")

        request = urllib.request.Request(
            f"{self.host}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise LLMUnavailable(f"Ollama endpoint failed: {exc}") from exc
        except (OSError, UnicodeDecodeError) as exc:  # connection refused, etc.
            raise LLMUnavailable(f"Ollama endpoint unreachable: {exc}") from exc

        message = body.get("message") if isinstance(body, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            raise LLMUnavailable("Ollama answered without a chat message")
        return content.strip()

    def status(self) -> str:
        """Probe `/api/tags` with a short timeout: is the server up AND the model pulled?"""
        try:
            with urllib.request.urlopen(f"{self.host}/api/tags", timeout=self.probe_timeout_s) as r:
                body = json.loads(r.read().decode("utf-8"))
        except Exception:
            return UNREACHABLE
        models = body.get("models", []) if isinstance(body, dict) else []
        names = {m.get("name") for m in models if isinstance(m, dict)}
        # Ollama lists an untagged model as "<name>:latest".
        wanted = self.model if ":" in self.model else f"{self.model}:latest"
        return CONNECTED if wanted in names else MODEL_MISSING

    def health(self) -> bool:
        return self.status() == CONNECTED
