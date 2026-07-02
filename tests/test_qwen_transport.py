# Aegis MemoryAgent — © 2026 Ben Duske. Licensed under the MIT License (see LICENSE).
"""Direct coverage for the Qwen Cloud TRANSPORT layer (qwen.py).

Every other test monkeypatches `qwen.chat`/`qwen.embed` away (see conftest), so
the actual HTTP client — URL assembly, the Bearer auth header, request shape,
response parsing, embedding index-ordering, and HTTP-error translation — had
zero direct coverage. These tests monkeypatch `urllib.request.urlopen` (so no
network is touched) to pin the guarantees that matter for a stdlib-only client.
"""
import io
import json
import urllib.error
import urllib.request

import pytest

from memoryagent import qwen, config


class _FakeResp:
    """Minimal context-manager stand-in for urlopen()'s return value."""
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._body


def _capture(monkeypatch, payload: dict):
    """Patch urlopen to record the Request and return `payload`. Returns a dict
    that fills with the captured request under key 'req'."""
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["req"] = req
        seen["timeout"] = timeout
        return _FakeResp(payload)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return seen


# --------------------------------------------------------------------------- #
# _post — URL, method, headers, body
# --------------------------------------------------------------------------- #

def test_post_builds_url_method_and_auth_header(monkeypatch):
    monkeypatch.setattr(config, "QWEN_BASE_URL", "https://example.test/v1/")
    monkeypatch.setattr(config, "QWEN_API_KEY", "sk-secret-123")
    seen = _capture(monkeypatch, {"ok": True})

    out = qwen._post("/chat/completions", {"hello": "world"})

    req = seen["req"]
    # trailing slash on the base is stripped, path appended verbatim
    assert req.full_url == "https://example.test/v1/chat/completions"
    assert req.get_method() == "POST"
    # header keys are capitalized by urllib; compare case-insensitively
    headers = {k.lower(): v for k, v in req.header_items()}
    assert headers["content-type"] == "application/json"
    assert headers["authorization"] == "Bearer sk-secret-123"
    # body is the JSON-encoded payload
    assert json.loads(req.data.decode("utf-8")) == {"hello": "world"}
    assert out == {"ok": True}
    assert seen["timeout"] == 120


def test_post_http_error_becomes_runtimeerror_with_code_and_detail(monkeypatch):
    monkeypatch.setattr(config, "QWEN_BASE_URL", "https://example.test/v1")
    monkeypatch.setattr(config, "QWEN_API_KEY", "sk-x")

    def raise_http(req, timeout=None):
        raise urllib.error.HTTPError(
            url=req.full_url, code=429, msg="Too Many Requests",
            hdrs=None, fp=io.BytesIO(b'{"error":"rate limited"}'),
        )

    monkeypatch.setattr(urllib.request, "urlopen", raise_http)

    with pytest.raises(RuntimeError) as ei:
        qwen._post("/chat/completions", {})
    msg = str(ei.value)
    assert "429" in msg
    assert "rate limited" in msg
    # chaining is deliberately suppressed (`from None`) so the raw HTTPError
    # (which can carry the key-bearing request) is not surfaced downstream.
    assert ei.value.__cause__ is None


# --------------------------------------------------------------------------- #
# chat — payload shape + content extraction
# --------------------------------------------------------------------------- #

def test_chat_sends_expected_payload_and_extracts_content(monkeypatch):
    monkeypatch.setattr(config, "QWEN_BASE_URL", "https://example.test/v1")
    monkeypatch.setattr(config, "QWEN_API_KEY", "sk-x")
    monkeypatch.setattr(config, "CHAT_MODEL", "qwen3.7-plus")
    seen = _capture(monkeypatch, {
        "choices": [{"message": {"content": "hello back"}}]
    })

    msgs = [{"role": "user", "content": "hi"}]
    out = qwen.chat(msgs)

    assert out == "hello back"
    req = seen["req"]
    assert req.full_url.endswith("/chat/completions")
    body = json.loads(req.data.decode("utf-8"))
    assert body["model"] == "qwen3.7-plus"        # default from config
    assert body["messages"] == msgs
    assert body["temperature"] == 0.4              # default


def test_chat_model_and_temperature_overrides_win(monkeypatch):
    monkeypatch.setattr(config, "QWEN_BASE_URL", "https://example.test/v1")
    monkeypatch.setattr(config, "QWEN_API_KEY", "sk-x")
    monkeypatch.setattr(config, "CHAT_MODEL", "qwen-default")
    seen = _capture(monkeypatch, {
        "choices": [{"message": {"content": "ok"}}]
    })

    qwen.chat([{"role": "user", "content": "x"}], model="qwen-max", temperature=0.9)

    body = json.loads(seen["req"].data.decode("utf-8"))
    assert body["model"] == "qwen-max"
    assert body["temperature"] == 0.9


# --------------------------------------------------------------------------- #
# embed — str→list coercion, model, and index-ordering
# --------------------------------------------------------------------------- #

def test_embed_wraps_single_string_and_uses_embed_model(monkeypatch):
    monkeypatch.setattr(config, "QWEN_BASE_URL", "https://example.test/v1")
    monkeypatch.setattr(config, "QWEN_API_KEY", "sk-x")
    monkeypatch.setattr(config, "EMBED_MODEL", "text-embedding-v4")
    seen = _capture(monkeypatch, {
        "data": [{"index": 0, "embedding": [0.1, 0.2]}]
    })

    out = qwen.embed("just one string")

    assert out == [[0.1, 0.2]]
    req = seen["req"]
    assert req.full_url.endswith("/embeddings")
    body = json.loads(req.data.decode("utf-8"))
    assert body["model"] == "text-embedding-v4"
    assert body["input"] == ["just one string"]   # coerced to a list


def test_embed_returns_vectors_in_index_order_regardless_of_response_order(monkeypatch):
    monkeypatch.setattr(config, "QWEN_BASE_URL", "https://example.test/v1")
    monkeypatch.setattr(config, "QWEN_API_KEY", "sk-x")
    # response deliberately OUT of order — client must sort by "index"
    seen = _capture(monkeypatch, {
        "data": [
            {"index": 2, "embedding": [2.0]},
            {"index": 0, "embedding": [0.0]},
            {"index": 1, "embedding": [1.0]},
        ]
    })

    out = qwen.embed(["a", "b", "c"])

    assert out == [[0.0], [1.0], [2.0]]
    body = json.loads(seen["req"].data.decode("utf-8"))
    assert body["input"] == ["a", "b", "c"]       # list passed through unchanged
