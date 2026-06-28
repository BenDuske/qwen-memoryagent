"""HTTP service tests — the FastAPI variant over the same memory engine.

Runs WITHOUT a Qwen Cloud key: the network calls are monkeypatched (same fakes
as the rest of the suite, via conftest), and the app is exercised in-process with
Starlette's TestClient. Skipped cleanly if FastAPI isn't installed, so the keyless
core suite never depends on the optional `service` extra.
"""
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
