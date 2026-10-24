"""LLM status monitor, env-driven configuration and structured logging."""

import io
import json
import logging
import threading
import time
from pathlib import Path

import pytest

from support_desk.config import Config
from support_desk.health import UNKNOWN, LLMStatusMonitor
from support_desk.logs import configure_logging

# --- health monitor -------------------------------------------------------- #


def test_monitor_never_blocks_and_refreshes_in_background():
    release = threading.Event()

    def slow_probe():
        release.wait(5)
        return "connected"

    monitor = LLMStatusMonitor(slow_probe, interval_s=60)
    started = time.perf_counter()
    assert monitor.state() == UNKNOWN
    assert monitor.state() == UNKNOWN  # a refresh is already running: no second thread
    assert time.perf_counter() - started < 0.5
    release.set()
    deadline = time.time() + 5
    while monitor.state() != "connected" and time.time() < deadline:
        time.sleep(0.01)
    assert monitor.state() == "connected"


def test_monitor_probe_errors_mean_unreachable(caplog):
    def broken():
        raise OSError("boom")

    assert LLMStatusMonitor(broken, 60).refresh() == "unreachable"
    assert "llm_probe_failed" in caplog.text


def test_monitor_mark_and_invalidate():
    monitor = LLMStatusMonitor(lambda: "unreachable", interval_s=60)
    monitor.mark("connected")
    assert monitor.state() == "connected"  # fresh: no probe
    monitor.invalidate()
    monitor.state()  # stale: starts a background probe
    deadline = time.time() + 5
    while monitor.state() != "unreachable" and time.time() < deadline:
        time.sleep(0.01)
    assert monitor.state() == "unreachable"


# --- config ---------------------------------------------------------------- #


def test_env_is_read_at_instantiation(monkeypatch):
    monkeypatch.setenv("SUPPORT_DESK_PORT", "8123")
    monkeypatch.setenv("SUPPORT_DESK_ESCALATION", "0.75")
    monkeypatch.setenv("SUPPORT_DESK_REFUND_CAP_MXN", "800")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5:0.5b")
    monkeypatch.setenv("SUPPORT_DESK_LOG_LEVEL", "debug")
    cfg = Config()
    assert (cfg.http_port, cfg.escalation_threshold, cfg.refund_cap_mxn) == (8123, 0.75, 800.0)
    assert cfg.model == "qwen2.5:0.5b" and cfg.log_level == "DEBUG"


def test_defaults(monkeypatch):
    for name in ("OLLAMA_MODEL", "SUPPORT_DESK_DB", "SUPPORT_DESK_PORT"):
        monkeypatch.delenv(name, raising=False)
    cfg = Config()
    assert cfg.model == "llama3.2:1b" and cfg.http_port == 8000
    assert cfg.temperature == 0.0 and cfg.refund_cap_mxn == 500.0
    project = Path(__file__).resolve().parent.parent
    assert Path(cfg.db_path).is_relative_to(Path.home())
    assert not Path(cfg.db_path).is_relative_to(project)


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("SUPPORT_DESK_PORT", "abc", "SUPPORT_DESK_PORT must be an integer"),
        ("SUPPORT_DESK_TIMEOUT_S", "fast", "SUPPORT_DESK_TIMEOUT_S must be a number"),
        ("SUPPORT_DESK_ESCALATION", "1.5", "between 0 and 1"),
        ("SUPPORT_DESK_REFUND_CAP_MXN", "-1", ">= 0"),
        ("SUPPORT_DESK_MAX_BODY_BYTES", "0", "> 0"),
        ("SUPPORT_DESK_LOG_LEVEL", "LOUD", "SUPPORT_DESK_LOG_LEVEL must be one of"),
    ],
)
def test_invalid_env_names_the_variable(monkeypatch, name, value, message):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=message):
        Config()


# --- logging --------------------------------------------------------------- #


def test_json_log_lines_carry_fields_and_exceptions():
    stream = io.StringIO()
    configure_logging("INFO", stream)
    log = logging.getLogger("support_desk.test")
    log.info("triage_decision", extra={"fields": {"decision_id": 7, "source": "llm"}})
    try:
        raise ValueError("bad")
    except ValueError:
        log.exception("failed")
    log.debug("hidden")
    first, second = (json.loads(line) for line in stream.getvalue().splitlines())
    assert first["event"] == "triage_decision" and first["decision_id"] == 7
    assert first["level"] == "INFO" and first["ts"].endswith("+00:00")
    assert second["event"] == "failed" and "ValueError: bad" in second["exc"]
