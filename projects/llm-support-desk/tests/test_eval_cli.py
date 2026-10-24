"""Evaluation harness and the command-line entry point."""

import json
import socket
from pathlib import Path

import pytest
from fakes import FakeLLM, StubOllama, answer

from support_desk import Config, TriageService, cli
from support_desk.evaluate import evaluate, fallback_service, format_report, load_labeled

CSV = str(Path(__file__).resolve().parent.parent / "data" / "sample_tickets.csv")
CFG = Config(db_path="")


def test_sample_tickets_carry_labels():
    rows = load_labeled(CSV)
    assert len(rows) == 23
    assert {r["must_escalate"] for r in rows} == {"yes", "no"}


def test_load_labeled_rejects_unlabeled_csv(tmp_path):
    path = tmp_path / "plain.csv"
    path.write_text("ticket_id,customer_text,amount\nT1,x,1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing columns"):
        load_labeled(path)


def test_fallback_eval_on_sample_tickets():
    """Pins the measured fallback numbers documented in the README."""
    m = evaluate(fallback_service(CFG), load_labeled(CSV))
    assert m["tickets"] == 23 and m["sources"] == {"llm": 0, "fallback": 23}
    assert m["category_agreement"] == 21
    assert [x["ticket_id"] for x in m["misclassified"]] == ["TK-1013", "TK-1016"]
    # Fallback confidence (0.5) is below the threshold: every ticket reaches a human.
    assert m["must_escalate_escalated"] == m["must_escalate"] == 10
    assert m["optional_escalated"] == 13 and m["first_line_actions"] == 0


def test_eval_report_with_a_confident_wrong_model():
    """A model that answers 'duplicate_charge' to everything: classification collapses,
    but the guardrails still escalate every ticket whose text or amount demands it."""
    m = evaluate(TriageService(CFG, llm=FakeLLM()), load_labeled(CSV))
    assert m["llm_answers"] == 23 and m["llm_category_agreement"] == 4
    # TK-1016 has no fraud wording and a $60 amount: only the model could have caught it.
    assert m["missed_escalations"] == ["TK-1016"]
    report = format_report("llm", "fake", CSV, m)
    assert "LLM answers that passed the schema: 23/23" in report
    assert "missed: TK-1016" in report


def closed_port_url():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return f"http://127.0.0.1:{sock.getsockname()[1]}"


def test_cli_eval_fallback_text(capsys):
    assert cli.main(["eval", "--mode", "fallback", "--csv", CSV]) == 0
    out = capsys.readouterr().out
    assert "category agreement (final decision): 21/23" in out


def test_cli_eval_json(capsys):
    assert cli.main(["eval", "--csv", CSV, "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["results"]["fallback"]["category_agreement"] == 21


def test_cli_eval_llm_unavailable(monkeypatch, capsys):
    monkeypatch.setenv("OLLAMA_HOST", closed_port_url())
    monkeypatch.setenv("SUPPORT_DESK_PROBE_TIMEOUT_S", "1")
    assert cli.main(["eval", "--mode", "llm", "--csv", CSV]) == 1
    assert "LLM not available" in capsys.readouterr().err
    assert cli.main(["eval", "--mode", "both", "--csv", CSV]) == 0
    assert "mode=fallback" in capsys.readouterr().out


def test_cli_eval_llm_against_stub_ollama(monkeypatch, capsys):
    stub = StubOllama()
    stub.tags_body = json.dumps({"models": [{"name": "stub:1b"}]})
    stub.chat_body = json.dumps({"message": {"content": answer(category="app_issue")}})
    monkeypatch.setenv("OLLAMA_HOST", stub.url)
    monkeypatch.setenv("OLLAMA_MODEL", "stub:1b")
    try:
        assert cli.main(["eval", "--mode", "both", "--csv", CSV]) == 0
    finally:
        stub.server.shutdown()
        stub.server.server_close()
    out = capsys.readouterr().out
    assert "mode=llm model=stub:1b" in out and "decided by: llm=23 fallback=0" in out
    assert stub.last_request["options"] == {"temperature": 0.0, "seed": 42}


def test_cli_metrics(tmp_path, capsys):
    db = str(tmp_path / "decisions.db")
    assert cli.main(["--db", db, "metrics"]) == 0
    assert json.loads(capsys.readouterr().out)["totals"]["decisions"] == 0
    assert cli.main(["--db", "", "metrics"]) == 2


def test_cli_invalid_env_exits_2(monkeypatch, capsys):
    monkeypatch.setenv("SUPPORT_DESK_PORT", "abc")
    assert cli.main(["metrics"]) == 2
    assert "SUPPORT_DESK_PORT must be an integer" in capsys.readouterr().err


def test_cli_serve_wires_store_probe_and_server(monkeypatch, tmp_path, capsys):
    seen = {}

    class FakeServer:
        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            seen["closed"] = True

    def fake_make_server(cfg, service):
        seen["service"] = service
        return FakeServer()

    monkeypatch.setenv("OLLAMA_HOST", closed_port_url())
    monkeypatch.setenv("SUPPORT_DESK_PROBE_TIMEOUT_S", "1")
    monkeypatch.setattr(cli, "make_server", fake_make_server)
    db = tmp_path / "d.db"
    assert cli.main(["--db", str(db), "--port", "8999", "--model", "m:1b"]) == 0
    assert seen["closed"] and seen["service"].store is not None and db.exists()
    assert seen["service"].cfg.http_port == 8999 and seen["service"].cfg.model == "m:1b"
    assert "(LLM: unreachable)" in capsys.readouterr().out
