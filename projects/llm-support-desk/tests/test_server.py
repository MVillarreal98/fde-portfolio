"""HTTP layer: status codes, input validation, liveness, metrics and the UI's XSS posture.

A real ThreadingHTTPServer runs on an ephemeral port; the LLM is faked.
"""

import http.client
import json
import re
import threading
import time

import pytest
from fakes import FakeLLM

from support_desk import Config, TriageService
from support_desk.server import PAGE, make_server
from support_desk.store import DecisionStore


def start(service):
    server = make_server(service.cfg, service)
    thread = threading.Thread(target=server.serve_forever, args=(0.05,), daemon=True)
    thread.start()
    return server


@pytest.fixture
def desk(tmp_path):
    cfg = Config(db_path="", http_host="127.0.0.1", http_port=0, max_body_bytes=1024)
    service = TriageService(cfg, llm=FakeLLM(), store=DecisionStore(str(tmp_path / "d.db")))
    server = start(service)
    yield server
    server.shutdown()
    server.server_close()


def call(server, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
    if isinstance(body, dict | list):
        body = json.dumps(body)
    conn.request(method, path, body=body, headers=headers or {})
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()
    ctype = resp.getheader("Content-Type", "")
    payload = json.loads(raw) if ctype.startswith("application/json") else raw.decode()
    return resp.status, payload, resp


# --- UI / XSS -------------------------------------------------------------- #


@pytest.mark.parametrize(
    "sink", ["innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "onclick="]
)
def test_page_has_no_html_injection_sinks(sink):
    assert sink not in PAGE


def test_page_renders_data_with_text_nodes():
    assert "node.textContent = String(text)" in PAGE
    assert "replaceChildren(card)" in PAGE


def test_served_page_has_csp_nonce_matching_its_only_script(desk):
    status, html, resp = call(desk, "GET", "/")
    assert status == 200 and "innerHTML" not in html
    csp = resp.getheader("Content-Security-Policy")
    nonce = re.search(r"'nonce-([^']+)'", csp).group(1)
    assert re.findall(r"<script[^>]*>", html) == [f'<script nonce="{nonce}">']
    assert "img-src 'none'" in csp and "unsafe-inline" not in csp.split("style-src")[0]
    assert resp.getheader("X-Content-Type-Options") == "nosniff"
    # a fresh nonce per response
    assert call(desk, "GET", "/")[2].getheader("Content-Security-Policy") != csp


# --- health ---------------------------------------------------------------- #


def test_health_reports_liveness_and_llm_state(desk):
    status, body, _ = call(desk, "GET", "/api/health")
    assert status == 200
    assert set(body) >= {"status", "llm", "llm_state", "model", "escalation_threshold"}


def test_health_never_waits_for_a_hanging_llm():
    class HangingProbe(FakeLLM):
        def status(self):
            time.sleep(3)
            return "connected"

    cfg = Config(db_path="", http_host="127.0.0.1", http_port=0)
    server = start(TriageService(cfg, llm=HangingProbe()))
    try:
        started = time.perf_counter()
        status, body, _ = call(server, "GET", "/api/health")
        elapsed = time.perf_counter() - started
    finally:
        server.shutdown()
        server.server_close()
    # Dockerfile HEALTHCHECK allows 2 s; liveness must not depend on Ollama at all.
    assert status == 200 and elapsed < 1.0
    assert body["status"] == "degraded" and body["llm_state"] == "unknown"


# --- POST /api/triage ------------------------------------------------------ #


def test_valid_triage_returns_persisted_decision(desk):
    status, body, _ = call(desk, "POST", "/api/triage", {"text": "charged twice", "amount": 50})
    assert status == 200 and body["source"] == "llm" and isinstance(body["decision_id"], int)


def test_optional_fields_may_be_null(desk):
    body = {"text": "charged twice", "amount": None, "history": None, "ticket_id": "TK-9"}
    status, payload, _ = call(desk, "POST", "/api/triage", body)
    assert status == 200 and payload["ticket_amount"] == 0.0


@pytest.mark.parametrize(
    ("body", "error"),
    [
        ("{not json", "body is not valid JSON"),
        (b"\xff\xfe", "body is not valid JSON"),
        ([1, 2], "body must be a JSON object"),
        ({"amount": 10}, "field 'text' is required"),
        ({"text": 123}, "field 'text' is required"),
        ({"text": "   "}, "field 'text' is required"),
        ({"text": "x", "amount": "mil pesos"}, "field 'amount' must be a number"),
        ({"text": "x", "amount": True}, "field 'amount' must be a number"),
        ({"text": "x", "amount": -5}, "finite number >= 0"),
        ('{"text": "x", "amount": NaN}', "finite number >= 0"),
        ('{"text": "x", "amount": 1e400}', "finite number >= 0"),
        ({"text": "x", "history": ["a"]}, "field 'history' must be a string"),
        ({"text": "x", "ticket_id": "T" * 65}, "field 'ticket_id'"),
    ],
)
def test_bad_requests_get_400_with_message(desk, body, error):
    status, payload, _ = call(desk, "POST", "/api/triage", body)
    assert status == 400 and error in payload["error"]


def test_oversized_body_gets_413(desk):
    status, payload, _ = call(desk, "POST", "/api/triage", {"text": "x" * 2000})
    assert status == 413 and "1024 bytes" in payload["error"]


def test_missing_or_invalid_content_length(desk):
    port = desk.server_address[1]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.putrequest("POST", "/api/triage")
    conn.endheaders()
    assert conn.getresponse().status == 411
    conn.close()
    for bad in ("abc", "-1"):
        status, payload, _ = call(desk, "POST", "/api/triage", "{}", {"Content-Length": bad})
        assert status == 400 and "Content-Length" in payload["error"]


def test_unknown_routes_get_404(desk):
    assert call(desk, "POST", "/api/other", {})[0] == 404
    assert call(desk, "GET", "/nope")[0] == 404
    assert call(desk, "PUT", "/api/triage", {})[0] == 501  # stdlib default, logged at DEBUG


def test_business_error_maps_to_422():
    class Rejecting(TriageService):
        def triage(self, *args, **kwargs):
            return {"error": "empty ticket text", "source": "input"}

    cfg = Config(db_path="", http_host="127.0.0.1", http_port=0)
    server = start(Rejecting(cfg, llm=FakeLLM()))
    try:
        assert call(server, "POST", "/api/triage", {"text": "x"})[0] == 422
    finally:
        server.shutdown()
        server.server_close()


def test_internal_errors_never_leak_details(caplog):
    class Exploding(TriageService):
        def triage(self, *args, **kwargs):
            raise RuntimeError("secret connection string")

        def llm_state(self):
            raise RuntimeError("secret probe detail")

    cfg = Config(db_path="", http_host="127.0.0.1", http_port=0)
    server = start(Exploding(cfg, llm=FakeLLM()))
    try:
        for method, path, body in [("POST", "/api/triage", {"text": "x"}),
                                   ("GET", "/api/health", None)]:  # fmt: skip
            status, payload, _ = call(server, method, path, body)
            assert status == 500 and payload == {"error": "internal error"}
    finally:
        server.shutdown()
        server.server_close()
    assert "secret connection string" in caplog.text  # details stay in the server log


# --- metrics --------------------------------------------------------------- #


def test_metrics_endpoint_counts_decisions(desk):
    call(desk, "POST", "/api/triage", {"text": "charged twice", "amount": 50})
    call(desk, "POST", "/api/triage", {"text": "No reconozco este cargo", "amount": 50})
    status, body, _ = call(desk, "GET", "/api/metrics")
    assert status == 200
    assert body["totals"]["decisions"] == 2 and body["totals"]["escalation_rate"] == 0.5
    assert {"rule": "fraud_signal", "decisions": 1} in body["rules_fired"]


def test_metrics_without_persistence_is_503():
    cfg = Config(db_path="", http_host="127.0.0.1", http_port=0)
    server = start(TriageService(cfg, llm=FakeLLM()))
    try:
        assert call(server, "GET", "/api/metrics")[0] == 503
    finally:
        server.shutdown()
        server.server_close()
