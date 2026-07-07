"""HTTP service tests — the FastAPI variant over the same memory engine.

Runs WITHOUT a Qwen Cloud key: the network calls are monkeypatched (same fakes
as the rest of the suite, via conftest), and the app is exercised in-process with
Starlette's TestClient. Skipped cleanly if FastAPI isn't installed, so the keyless
core suite never depends on the optional `service` extra.
"""
import threading
import time

import pytest

pytest.importorskip("fastapi", reason="install the 'service' extra to run app tests")
from fastapi.testclient import TestClient  # noqa: E402

from memoryagent import app as app_module  # noqa: E402


@pytest.fixture
def client(patched, monkeypatch):
    # `patched` points MEMORY_DIR at a temp dir and fakes qwen.embed/chat.
    # Clear the per-process agent cache so each test gets a clean store.
    monkeypatch.setattr(app_module, "_AGENTS", {})
    return TestClient(app_module.app)


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_chat_returns_reply_and_stats(client):
    r = client.post("/chat", json={"user": "ben", "text": "hello there"})
    assert r.status_code == 200
    body = r.json()
    assert body["reply"] == "ok (stubbed reply)"
    assert "facts" in body["stats"]


def test_cross_session_recall_persists_across_users(client):
    # Teach a fact in one request; the extraction stub turns "peanut" into a fact.
    client.post("/chat", json={"user": "ben", "text": "I am allergic to peanuts"})

    # A brand-new request (new logical session) recalls it — no history replayed.
    r = client.get("/memory/ben/recall", params={"q": "what foods are unsafe for me"})
    assert r.status_code == 200
    texts = " ".join(item["text"].lower() for item in r.json()["recalled"])
    assert "peanut" in texts


def test_recall_is_isolated_per_user(client):
    client.post("/chat", json={"user": "ben", "text": "I am allergic to peanuts"})
    r = client.get("/memory/alice/recall", params={"q": "allergies"})
    assert r.status_code == 200
    assert r.json()["recalled"] == []  # alice's store never saw ben's memory


def test_recall_respects_token_budget(client):
    for i in range(20):
        client.post("/chat", json={
            "user": "ben",
            "text": f"call me Ben and remember hiking mountains fact {i}",
        })
    r = client.get("/memory/ben/recall",
                   params={"q": "hiking mountains", "budget": 40, "top_k": 100})
    assert r.status_code == 200
    recalled = r.json()["recalled"]
    used = sum(max(1, len(item["text"]) // 4) for item in recalled)
    assert used <= 40, f"service recall overflowed budget: {used} > 40"


def test_forget_endpoint(client):
    client.post("/chat", json={"user": "ben", "text": "just chatting about the weather"})
    r = client.post("/memory/ben/forget")
    assert r.status_code == 200
    assert "dropped" in r.json()


def test_stats_endpoint(client):
    # Teach one fact, then read stats directly via the dedicated endpoint.
    client.post("/chat", json={"user": "ben", "text": "I am allergic to peanuts"})
    r = client.get("/memory/ben/stats")
    assert r.status_code == 200
    body = r.json()
    assert body["facts"] >= 1
    assert {"facts", "episodes", "prefs"} <= set(body)


def test_agent_for_is_race_safe_for_new_user(patched, monkeypatch):
    # FastAPI serves sync handlers from a threadpool, so concurrent requests for
    # the SAME new user race the get-or-create in _agent_for. Two stores over one
    # on-disk root => full-file rewrites clobber each other => lost writes. Pin
    # that exactly one MemoryStore is built and every caller gets that one object.
    monkeypatch.setattr(app_module, "_AGENTS", {})

    builds = []
    builds_lock = threading.Lock()
    real_store = app_module.MemoryStore

    def counting_store(*args, **kwargs):
        # Widen the construct window so the unguarded race is near-certain to
        # double-build; with the lock, only the first thread ever gets here.
        time.sleep(0.02)
        with builds_lock:
            builds.append(1)
        return real_store(*args, **kwargs)

    monkeypatch.setattr(app_module, "MemoryStore", counting_store)

    n = 8
    barrier = threading.Barrier(n)
    got = []
    got_lock = threading.Lock()

    def worker():
        barrier.wait()  # release all threads into _agent_for at once
        a = app_module._agent_for("racer")
        with got_lock:
            got.append(a)

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sum(builds) == 1, f"expected exactly one store build, got {sum(builds)}"
    assert len(got) == n
    assert all(a is got[0] for a in got), "callers got different agent instances"
    assert app_module._AGENTS["racer"] is got[0]


def test_chat_engine_error_surfaces_as_502(client, monkeypatch):
    # A failure inside the memory engine (e.g. Qwen Cloud unreachable) must be
    # reported as a 502 Bad Gateway, not a bare 500 — pins the `except` guard.
    agent = app_module._agent_for("ben")

    def boom(text):
        raise RuntimeError("qwen cloud unreachable")

    monkeypatch.setattr(agent, "chat", boom)
    r = client.post("/chat", json={"user": "ben", "text": "hello"})
    assert r.status_code == 502
    assert "qwen cloud unreachable" in r.json()["detail"]


def test_recall_engine_error_surfaces_as_502(client, monkeypatch):
    # /recall embeds the query via Qwen Cloud, so an upstream failure (e.g. a
    # missing/expired key) must degrade to a 502 with detail — the same graceful
    # surface /chat gives — not a bare 500. Pins the recall `except` guard.
    agent = app_module._agent_for("ben")

    def boom(q, token_budget=None, top_k=None):
        raise RuntimeError("qwen cloud unreachable")

    monkeypatch.setattr(agent.mem, "recall", boom)
    r = client.get("/memory/ben/recall", params={"q": "snack allergy"})
    assert r.status_code == 502
    assert "qwen cloud unreachable" in r.json()["detail"]
