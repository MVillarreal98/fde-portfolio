"""Stdlib HTTP server + embedded operator UI.

Zero extra dependencies: runs on any corporate workstation image. The UI is a
single page where an operator pastes a claim and sees the structured decision,
the rules that fired and the decision source (llm/fallback) in one screen.

Model output and customer text are untrusted: the page builds every node with
textContent (no innerHTML), and a per-response CSP nonce blocks inline handlers.
Bad requests get a 4xx JSON error; unexpected failures a generic 500 (details
only in the server log, never a traceback to the client).
"""

from __future__ import annotations

import json
import logging
import math
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from . import __version__
from .health import UNKNOWN
from .llm_client import CONNECTED
from .prompts import PROMPT_VERSION
from .service import TriageService

log = logging.getLogger(__name__)

# Oversized bodies are read and discarded up to this size before answering 413.
DRAIN_MAX_BYTES = 1 << 20

PAGE = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Support Desk — Triage Agent</title>
<style>
  :root { font-family: system-ui, sans-serif; }
  body { margin: 0; display: grid; grid-template-columns: 420px 1fr; height: 100vh; }
  aside { background: #0f1c2e; color: #e7eef7; padding: 24px; }
  aside h1 { font-size: 20px; margin: 0 0 4px; }
  aside .sub { color: #93a7bf; font-size: 13px; margin-bottom: 20px; }
  label { display: block; font-size: 12px; margin: 12px 0 4px; color: #93a7bf; }
  textarea, input { width: 100%; box-sizing: border-box; border: 1px solid #2c425e;
    background: #16293f; color: #e7eef7; border-radius: 8px; padding: 10px; font: inherit; }
  textarea { height: 150px; resize: vertical; }
  button { margin-top: 16px; width: 100%; padding: 12px; border: 0; border-radius: 8px;
    background: #118d57; color: white; font-weight: 600; cursor: pointer; }
  button:disabled { background: #2c425e; cursor: wait; }
  main { padding: 24px; overflow-y: auto; background: #f2f5f9; }
  .health { font-size: 12px; padding: 6px 10px; border-radius: 999px; display: inline-block; }
  .health.ok { background: #dcf5e7; color: #0c6b3d; }
  .health.down { background: #fbe3e3; color: #8f2424; }
  .card { background: white; border: 1px solid #dde4ee; border-radius: 12px; padding: 18px; margin-bottom: 14px; }
  .badge { display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; margin-right: 4px; }
  .badge.high { background: #fbe3e3; color: #8f2424; } .badge.medium { background: #fdeedc; color: #92510f; }
  .badge.low { background: #e7f2fd; color: #1d5f9c; }
  .badge.ok { background: #dcf5e7; color: #0c6b3d; }
  .badge.esc { background: #f6e3fb; color: #7c2c8f; }
  dl { margin: 8px 0 0; } dt { font-size: 11px; color: #7b8798; text-transform: uppercase; }
  dd { margin: 2px 0 10px; font-size: 14px; white-space: pre-wrap; }
  dd.action { font-weight: 700; }
</style>
</head>
<body>
<aside>
  <h1>🧾 Support Desk — Triage Agent</h1>
  <div class="sub">Local-LLM claim classifier · rules-enforced · Ollama REST</div>
  <span id="health" class="health down">checking local inference…</span>
  <label for="text">Customer's claim</label>
  <textarea id="text" placeholder="Describe el reclamo del cliente + evidencia…"></textarea>
  <label for="amount">Amount at stake (MXN)</label>
  <input id="amount" type="number" step="0.01" min="0" value="0.00">
  <label for="history">Customer history (optional)</label>
  <textarea id="history" placeholder="e.g. 12 transactions last 30 days, avg $85" style="height:80px"></textarea>
  <button id="go">Classify claim</button>
</aside>
<main id="out">
  <div class="card"><strong>Ready.</strong> Paste a claim on the left. The model proposes a
  schema-validated JSON decision; deterministic business rules decide the final action
  (refund cap, fraud signals, escalation threshold, unauthorized-charge override).</div>
</main>
<script nonce="__NONCE__">
let threshold = 0.6;
function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = String(text);
  return node;
}
function render(d) {
  const card = el('div', 'card');
  if (d.error) {
    card.append(el('h2', null, '⚠️ ' + d.error));
    document.getElementById('out').replaceChildren(card);
    return;
  }
  const title = el('h2', null, String(d.category).replace(/_/g, ' '));
  title.style.marginTop = '0';
  const sev = ['low', 'medium', 'high'].includes(d.severity) ? d.severity : 'high';
  const badges = el('div');
  badges.append(
    el('span', 'badge ' + sev, sev + ' severity'),
    el('span', 'badge low', 'source: ' + d.source),
    d.escalated ? el('span', 'badge esc', 'escalated to human') : el('span', 'badge ok', 'first-line ready'),
    el('span', 'badge ' + (d.confidence > threshold ? 'ok' : 'medium'), 'confidence ' + d.confidence),
  );
  const dl = el('dl');
  const row = (label, value, cls) => dl.append(el('dt', null, label), el('dd', cls, value));
  row('Action (decided by rules)', d.action, 'action');
  row('Money at stake', '$' + Number(d.exposure_mxn || 0).toFixed(2) + ' MXN');
  if (d.rules_applied && d.rules_applied.length) row('Rules applied', d.rules_applied.join(', '));
  row(d.source === 'llm' ? 'Summary (model, advisory)' : 'Summary (keyword fallback)', d.summary || '');
  row('Suggested resolution', d.suggested_resolution || '');
  if (d.fallback_note) row('Fallback note', d.fallback_note);
  row('Audit', (d.decision_id ? 'decision #' + d.decision_id + ' · ' : '') + 'prompt ' + d.prompt_version
      + (d.model ? ' · model ' + d.model : ''));
  card.append(title, badges, dl);
  document.getElementById('out').replaceChildren(card);
}
async function triage() {
  const btn = document.getElementById('go'); btn.disabled = true;
  try {
    const res = await fetch('/api/triage', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        text: document.getElementById('text').value,
        amount: parseFloat(document.getElementById('amount').value || '0'),
        history: document.getElementById('history').value
      })});
    render(await res.json());
  } catch (err) {
    render({error: 'request failed: ' + err});
  } finally {
    btn.disabled = false;
  }
}
function refreshHealth() {
  fetch('/api/health').then(r => r.json()).then(h => {
    const el = document.getElementById('health');
    threshold = h.escalation_threshold ?? threshold;
    const labels = {connected: 'local inference: connected (' + h.model + ')',
      model_missing: 'local inference: model ' + h.model + ' not pulled — fallback active',
      unreachable: 'local inference: down — fallback active',
      unknown: 'local inference: checking…'};
    el.textContent = labels[h.llm_state] || labels.unknown;
    el.className = 'health ' + (h.llm ? 'ok' : 'down');
  }).catch(() => {});
}
document.getElementById('go').addEventListener('click', triage);
refreshHealth();
setInterval(refreshHealth, 15000);
</script>
</body></html>"""

# The nonce is the only script allowed to run; inline handlers (onerror=...) are blocked.
CSP = (
    "default-src 'none'; script-src 'nonce-{nonce}'; style-src 'unsafe-inline'; "
    "connect-src 'self'; img-src 'none'; base-uri 'none'; form-action 'none'"
)


class BadRequest(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def parse_triage_request(body: bytes) -> tuple[str, float, str, str | None]:
    """Validate a POST /api/triage body; raise BadRequest(400) with a clear message."""
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise BadRequest(400, "body is not valid JSON") from None
    if not isinstance(payload, dict):
        raise BadRequest(400, "body must be a JSON object")

    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise BadRequest(400, "field 'text' is required and must be a non-empty string")
    amount = payload.get("amount", 0)
    if amount is None:
        amount = 0
    if isinstance(amount, bool) or not isinstance(amount, int | float):
        raise BadRequest(400, "field 'amount' must be a number")
    if not math.isfinite(amount) or amount < 0:
        raise BadRequest(400, "field 'amount' must be a finite number >= 0")
    history = payload.get("history") or ""
    if not isinstance(history, str):
        raise BadRequest(400, "field 'history' must be a string")
    ticket_id = payload.get("ticket_id")
    if ticket_id is not None and (not isinstance(ticket_id, str) or len(ticket_id) > 64):
        raise BadRequest(400, "field 'ticket_id' must be a string of at most 64 characters")
    return text, float(amount), history, ticket_id


class Handler(BaseHTTPRequestHandler):
    service: TriageService
    server_version = "SupportDesk"
    sys_version = ""

    def _send(self, code: int, body: bytes, ctype: str, headers: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload: dict) -> None:
        # allow_nan=False: the UI must always receive valid JSON.
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self._send(code, body, "application/json; charset=utf-8")

    def do_GET(self) -> None:
        try:
            path = urlsplit(self.path).path
            if path == "/":
                nonce = secrets.token_urlsafe(16)
                page = PAGE.replace("__NONCE__", nonce).encode("utf-8")
                csp = {"Content-Security-Policy": CSP.format(nonce=nonce)}
                self._send(200, page, "text/html; charset=utf-8", csp)
            elif path == "/api/health":
                self._json(200, self._health())
            elif path == "/api/metrics":
                if self.service.store is None:
                    self._json(503, {"error": "persistence disabled (SUPPORT_DESK_DB is empty)"})
                else:
                    self._json(200, self.service.store.metrics())
            else:
                self._json(404, {"error": "not found"})
        except Exception:
            log.exception("http_get_failed", extra={"fields": {"path": self.path}})
            self._json(500, {"error": "internal error"})

    def _health(self) -> dict:
        """Liveness: answers from cached state only, so it is fast even if Ollama hangs."""
        state = self.service.llm_state()
        return {
            "status": "ok" if state == CONNECTED else "degraded",
            "llm": state == CONNECTED,
            "llm_state": state if state else UNKNOWN,
            "model": self.service.cfg.model,
            "escalation_threshold": self.service.cfg.escalation_threshold,
            "refund_cap_mxn": self.service.cfg.refund_cap_mxn,
            "prompt_version": PROMPT_VERSION,
            "persistence": self.service.store is not None,
            "version": __version__,
        }

    def do_POST(self) -> None:
        try:
            if urlsplit(self.path).path != "/api/triage":
                self._json(404, {"error": "not found"})
                return
            body = self._read_body()
            text, amount, history, ticket_id = parse_triage_request(body)
            decision = self.service.triage(text, amount, history, ticket_ref=ticket_id)
            self._json(422 if "error" in decision else 200, decision)
        except BadRequest as exc:
            self._json(exc.status, {"error": exc.message})
        except Exception:
            log.exception("http_post_failed", extra={"fields": {"path": self.path}})
            self._json(500, {"error": "internal error"})

    def _read_body(self) -> bytes:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise BadRequest(411, "Content-Length header is required")
        try:
            length = int(raw_length)
        except ValueError:
            raise BadRequest(400, "invalid Content-Length header") from None
        if length < 0:
            raise BadRequest(400, "invalid Content-Length header")
        limit = self.service.cfg.max_body_bytes
        if length > limit:
            # Drain (bounded) so the client reads the 413 instead of a connection reset.
            self.rfile.read(min(length, DRAIN_MAX_BYTES))
            self.close_connection = True
            raise BadRequest(413, f"body larger than {limit} bytes")
        return self.rfile.read(length)

    def log_request(self, code="-", size="-") -> None:
        log.info(
            "http_request",
            extra={
                "fields": {
                    "method": self.command,
                    "path": urlsplit(self.path).path,
                    "status": int(code) if str(code).isdigit() else code,
                    "client": self.client_address[0],
                }
            },
        )

    def log_message(self, format, *args) -> None:  # route stdlib messages to logging
        log.debug("http_server", extra={"fields": {"message": format % args}})


def make_server(cfg, service: TriageService | None = None) -> ThreadingHTTPServer:
    svc = service or TriageService(cfg)
    handler = type("BoundHandler", (Handler,), {"service": svc})
    server = ThreadingHTTPServer((cfg.http_host, cfg.http_port), handler)
    server.daemon_threads = True
    return server
