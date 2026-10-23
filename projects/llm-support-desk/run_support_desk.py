"""CLI entry point: starts the operator UI at http://localhost:8000."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent / "src"))

from support_desk import Config, TriageService  # noqa: E402
from support_desk.server import make_server  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Support Desk Triage Agent (local LLM).")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--host", type=str, default=None)
    parser.add_argument("--model", type=str, default=None)
    args = parser.parse_args()

    cfg = Config()
    cfg.http_host = args.host or cfg.http_host
    cfg.http_port = args.port or cfg.http_port
    cfg.model = args.model or cfg.model

    service = TriageService(cfg)
    connected = service.llm.health()
    print(f"[ok] Local inference: {'connected — ' + cfg.model if connected else 'not reachable — deterministic fallback active'}")
    print(f"[ok] Support Desk UI: http://{cfg.http_host}:{cfg.http_port}")

    server = make_server(cfg, service)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[ok] Support Desk shut down.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
