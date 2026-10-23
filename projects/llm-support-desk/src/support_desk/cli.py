"""Command-line entry point (console script `support-desk` via pyproject)."""

from __future__ import annotations

import argparse

from . import Config, TriageService
from .server import make_server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Support Desk Triage Agent (local LLM).")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--host", type=str, default=None)
    parser.add_argument("--model", type=str, default=None)
    args = parser.parse_args(argv)

    cfg = Config()
    cfg.http_host = args.host or cfg.http_host
    cfg.http_port = args.port or cfg.http_port
    cfg.model = args.model or cfg.model

    service = TriageService(cfg)
    connected = service.llm.health()
    llm_status = (
        f"connected — {cfg.model}" if connected else "not reachable — deterministic fallback active"
    )
    print(f"[ok] Local inference: {llm_status}")
    print(f"[ok] Support Desk UI: http://{cfg.http_host}:{cfg.http_port}")

    server = make_server(cfg, service)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[ok] Support Desk shut down.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
