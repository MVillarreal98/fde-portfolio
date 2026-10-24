"""Command-line entry point (console script `support-desk` via pyproject).

support-desk [--port N] [--host H] [--model M] [--db PATH]    # serve (default)
support-desk eval [--mode fallback|llm|both] [--csv FILE] [--json]
support-desk metrics [--db PATH]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from . import Config, TriageService
from .evaluate import DEFAULT_CSV, evaluate, fallback_service, format_report, load_labeled
from .llm_client import CONNECTED
from .logs import configure_logging
from .server import make_server
from .store import DecisionStore

log = logging.getLogger("support_desk.cli")  # not __name__: "__main__" under python -m


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="support-desk", description="Support Desk Triage Desk (local LLM + rules)."
    )
    parser.add_argument("--port", type=int, help="HTTP port (env SUPPORT_DESK_PORT, 8000)")
    parser.add_argument("--host", help="bind address (env SUPPORT_DESK_HOST, localhost)")
    parser.add_argument("--model", help="Ollama model (env OLLAMA_MODEL, llama3.2:1b)")
    parser.add_argument("--db", help="SQLite decision log (env SUPPORT_DESK_DB); '' disables")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("serve", help="run the operator UI and API (default)")
    ev = sub.add_parser("eval", help="measure agreement against the labeled tickets")
    ev.add_argument("--mode", choices=("fallback", "llm", "both"), default="fallback")
    ev.add_argument("--csv", default=DEFAULT_CSV, help=f"labeled tickets (default {DEFAULT_CSV})")
    ev.add_argument("--json", action="store_true", help="print machine-readable results")
    sub.add_parser("metrics", help="print SQL metrics from the decision log as JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        cfg = Config()
    except ValueError as exc:
        print(f"[error] invalid configuration: {exc}", file=sys.stderr)
        return 2
    cfg.http_host = args.host or cfg.http_host
    cfg.http_port = args.port or cfg.http_port
    cfg.model = args.model or cfg.model
    if args.db is not None:
        cfg.db_path = args.db
    # Eval prints its own report; per-decision INFO lines would only bury it.
    quiet = args.command == "eval" and cfg.log_level == "INFO"
    configure_logging("WARNING" if quiet else cfg.log_level)

    if args.command == "eval":
        return run_eval(cfg, args.mode, args.csv, args.json)
    if args.command == "metrics":
        if not cfg.db_path:
            print("[error] persistence disabled: set SUPPORT_DESK_DB or --db", file=sys.stderr)
            return 2
        print(json.dumps(DecisionStore(cfg.db_path).metrics(), indent=2))
        return 0
    return serve(cfg)


def serve(cfg: Config) -> int:
    store = DecisionStore(cfg.db_path) if cfg.db_path else None
    service = TriageService(cfg, store=store)
    llm_state = service.monitor.refresh()  # bounded by SUPPORT_DESK_PROBE_TIMEOUT_S
    server = make_server(cfg, service)
    log.info(
        "server_started",
        extra={
            "fields": {
                "url": f"http://{cfg.http_host}:{cfg.http_port}",
                "model": cfg.model,
                "llm_state": llm_state,
                "db_path": cfg.db_path or None,
            }
        },
    )
    print(f"[ok] Support Desk UI: http://{cfg.http_host}:{cfg.http_port} (LLM: {llm_state})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[ok] Support Desk shut down.")
    finally:
        server.server_close()
    return 0


def run_eval(cfg: Config, mode: str, csv_path: str, as_json: bool) -> int:
    rows = load_labeled(csv_path)
    results = {}
    if mode in ("fallback", "both"):
        results["fallback"] = evaluate(fallback_service(cfg), rows)
    exit_code = 0
    if mode in ("llm", "both"):
        service = TriageService(cfg)  # no store: evaluation never pollutes the decision log
        state = service.monitor.refresh()
        if state == CONNECTED:
            results["llm"] = evaluate(service, rows)
        else:
            print(f"[warn] LLM not available (state={state}); skipping llm mode", file=sys.stderr)
            exit_code = 1 if mode == "llm" else 0

    if as_json:
        print(json.dumps({"model": cfg.model, "csv": csv_path, "results": results}, indent=2))
    else:
        for name, metrics in results.items():
            model = cfg.model if name == "llm" else None
            print(format_report(name, model, csv_path, metrics))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
