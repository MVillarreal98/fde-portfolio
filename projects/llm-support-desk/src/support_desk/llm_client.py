"""Ollama REST client over urllib.

Deliberately dependency-free: fintech environments often cannot add packages to
the workstation image; urllib keeps the same behavior everywhere.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request


class LLMUnavailable(Exception):
    """Raised when the local inference endpoint is down, slow or wrong."""


class OllamaClient:
    """Thin wrapper around `POST {host}/api/chat` with `format: "json"`.

    Forcing JSON at the protocol level (not just politely asking in the prompt)
    is what makes the downstream schema contract trustworthy.
    """

    def __init__(self, host: str, model: str, timeout_s: int = 90) -> None:
        self.host = host.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s

    def chat(self, messages: list[dict]) -> str:
        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            "stream": False,
            "format": "json",  # protocol-level JSON mode
        }).encode("utf-8")

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
        except OSError as exc:  # connection refused, etc.
            raise LLMUnavailable(f"Ollama endpoint unreachable: {exc}") from exc

        content = body.get("message", {}).get("content", "")
        return content.strip()

    def health(self) -> bool:
        try:
            with urllib.request.urlopen(
                f"{self.host}/api/tags", timeout=3.0
            ) as resp:
                return resp.status == 200
        except Exception:
            return False
