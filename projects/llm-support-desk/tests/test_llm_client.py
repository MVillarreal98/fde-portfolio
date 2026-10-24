"""OllamaClient against a stub Ollama HTTP server (no inference needed)."""

import json
import socket

import pytest
from fakes import StubOllama

from support_desk.llm_client import (
    CONNECTED,
    MODEL_MISSING,
    UNREACHABLE,
    LLMUnavailable,
    OllamaClient,
)


@pytest.fixture
def stub():
    s = StubOllama()
    yield s
    s.server.shutdown()
    s.server.server_close()


def closed_port_url():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return f"http://127.0.0.1:{sock.getsockname()[1]}"


def test_chat_sends_json_mode_and_deterministic_options(stub):
    client = OllamaClient(stub.url + "/", "llama3.2:1b", 5, temperature=0.0, seed=7)
    assert client.chat([{"role": "user", "content": "hi"}]) == "{}"
    req = stub.last_request
    assert req["format"] == "json" and req["stream"] is False
    assert req["options"] == {"temperature": 0.0, "seed": 7}
    assert req["model"] == "llama3.2:1b"


@pytest.mark.parametrize(
    ("status", "body", "message"),
    [
        (200, "[]", "without a chat message"),
        (200, '{"message": "oops"}', "without a chat message"),
        (200, "not json", "Ollama endpoint failed"),
        (404, '{"error": "model not found"}', "Ollama endpoint failed"),
    ],
)
def test_chat_errors_become_llm_unavailable(stub, status, body, message):
    stub.chat_status, stub.chat_body = status, body
    with pytest.raises(LLMUnavailable, match=message):
        OllamaClient(stub.url, "llama3.2:1b", 5).chat([])


def test_chat_dropped_connection_becomes_llm_unavailable(stub):
    stub.chat_status = None
    with pytest.raises(LLMUnavailable, match="unreachable"):
        OllamaClient(stub.url, "llama3.2:1b", 5).chat([])


def test_chat_timeout_becomes_llm_unavailable(stub):
    stub.delay_s = 1.0
    with pytest.raises(LLMUnavailable):
        OllamaClient(stub.url, "llama3.2:1b", 0.2).chat([])


def test_chat_connection_refused_becomes_llm_unavailable():
    with pytest.raises(LLMUnavailable):
        OllamaClient(closed_port_url(), "llama3.2:1b", 2).chat([])


def test_status_checks_that_the_model_is_pulled(stub):
    assert OllamaClient(stub.url, "llama3.2:1b").status() == CONNECTED
    assert OllamaClient(stub.url, "llama3.2:1b").health() is True
    # "llama3.2" means "llama3.2:latest", which is not pulled here
    assert OllamaClient(stub.url, "llama3.2").status() == MODEL_MISSING
    stub.tags_body = json.dumps({"models": [{"name": "llama3.2:latest"}]})
    assert OllamaClient(stub.url, "llama3.2").status() == CONNECTED
    stub.tags_body = "[]"
    assert OllamaClient(stub.url, "llama3.2:1b").status() == MODEL_MISSING


def test_status_unreachable():
    client = OllamaClient(closed_port_url(), "llama3.2:1b", probe_timeout_s=1)
    assert client.status() == UNREACHABLE and client.health() is False
