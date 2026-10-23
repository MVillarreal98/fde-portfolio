"""Stdlib HTTP server + embedded operator UI.

Zero extra dependencies: runs on any corporate workstation image. The UI is a
single page where an operator pastes a claim and sees the structured decision,
its rules-audits and the decision source (llm/fallback) in one screen.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from .service import TriageService

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
  .badge { display: inline-block; padding: 3px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; }
  .badge.high { background: #fbe3e3; color: #8f2424; } .badge.medium { background: #fdeedc; color: #92510f; }
  .badge.low { background: #e7f2fd; color: #1d5f9c; }
  .badge.esc { background: #f6e3fb; color: #7c2c8f; }
  dl { margin: 8px 0 0; } dt { font-size: 11px; color: #7b8798; text-transform: uppercase; }
  dd { margin: 2px 0 10px; font-size: 14px; }
</style>
</head>
<body>
<aside>
  <h1>🧾 Support Desk — Triage Agent</h1>
  <div class="sub">Local-LLM claim classifier · rules-enforced · Ollama REST</div>
  <span id="health" class="health down">checking local inference…</span>
  <label>Customer's claim</label>
  <textarea id="text" placeholder="Describe el reclamo del cliente +evidence…"></textarea>
  <label>Amount at stake (MXN)</label>
  <input id="amount" type="number" step="0.01" value="0.00">
  <label>Customer history (optional)</label>
  <textarea id="history" placeholder="e.g. 12 transactions last 30 days, avg $85" style="height:80px"></textarea>
  <button id="go" onclick="triage()">Classify claim</button>
</aside>
<main id="out">
  <div class="card"><strong>Ready.</strong> Paste a claim on the left. The agent returns a
  schema-validated JSON decision, post-processed by the deterministic business rules
  (refund cap, escalation threshold, unauthorized-charge override).</div>
</main>
<script>
async function triage() {
  const btn = document.getElementById('go'); btn.disabled = true;
  const res = await fetch('/api/triage', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({
      text: document.getElementById('text').value,
      amount: parseFloat(document.getElementById('amount').value || '0'),
      history: document.getElementById('history').value
    })});
  const d = await res.json(); btn.disabled = false; render(d);
}
function badge(seg, cls) { return `<span class="badge ${cls}">${seg}</span>`; }
function render(d) {
  document.getElementById('out').innerHTML = `
  <div class="card">
    <h2 style="margin-top:0">${d.error ? '⚠️ ' + d.error : d.category.replace(/_/g,' ')}</h2>
    ${d.error ? '' : [
      badge((d.severity||'low') + ' severity', d.severity||'low'),
      badge('source: ' + d.source, 'low'),
      d.escalated ? badge('escalated to human', 'esc') : badge('first-line ready', 'ok'),
      badge('confidence ' + (d.confidence ?? 0), d.confidence >= .6 ? 'ok' : 'medium'),
    ].join(' ')}
    ${d.error ? '' : `<dl>
      <dt>Amount at risk</dt><dd>$${(d.amount_at_risk ?? d.ticket_amount ?? 0).toFixed(2)} MXN</dd>
      <dt>Summary</dt><dd>${d.summary ?? ''}</dd>
      <dt>Suggested resolution</dt><dd>${d.suggested_resolution ?? ''}</dd>
      ${d.fallback_note ? `<dt>Fallback note</dt><dd>${d.fallback_note}</dd>` : ''}
    </dl>`}
  </div>`;
}
fetch('/api/health').then(r=>r.json()).then(h=>{
  const el = document.getElementById('health');
  el.textContent = h.llm ? 'local inference: connected (' + h.model + ')' : 'local inference: down — fallback active';
  el.className = 'health ' + (h.llm ? 'ok' : 'down');
});
</script>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    service: TriageService

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/" :
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        elif path == "/api/health":
            body = json.dumps({"llm": self.service.llm.health(), "model": self.service.cfg.model})
            self._send(200, body.encode(), "application/json")
        else:
            self._send(404, b'{"error": "not found"}', "application/json")

    def do_POST(self) -> None:
        if urlsplit(self.path).path != "/api/triage":
            self._send(404, b'{"error": "not found"}', "application/json")
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        decision = self.service.triage(
            payload.get("text", ""), float(payload.get("amount", 0) or 0),
            payload.get("history", ""),
        )
        self._send(200, json.dumps(decision, ensure_ascii=False).encode(), "application/json")

    def log_message(self, *args) -> None:  # keep the operator console readable
        pass


def make_server(cfg, service: TriageService | None = None) -> ThreadingHTTPServer:
    svc = service or TriageService(cfg)
    Handler.service = svc
    return ThreadingHTTPServer((cfg.http_host, cfg.http_port), Handler)
