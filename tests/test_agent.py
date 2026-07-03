"""MemoryAgent turn loop: recall -> answer -> learn -> forget, and cross-session recall."""
import pytest

from memoryagent import qwen
from memoryagent.memory import MemoryStore
from memoryagent.agent import MemoryAgent
from conftest import make_fake_chat


def test_chat_returns_reply_and_learns_memory(agent):
    reply = agent.chat("Please call me Ada, and note I'm allergic to peanuts.")
    assert isinstance(reply, str) and reply

    # The fake extractor pulls a fact + a pref from that message.
    assert any("allergic" in f["text"].lower() for f in agent.mem.facts)
    assert agent.mem.prefs.get("name", {}).get("value") == "ada"


def test_recalled_memory_is_injected_into_system_prompt(monkeypatch, patched):
    seen = []
    monkeypatch.setattr(qwen, "chat", make_fake_chat(record=seen))
    agent = MemoryAgent(MemoryStore(root=str(patched / "inject")))

    agent.mem.add_fact("The user is allergic to peanuts")
    agent.chat("What snacks can I have?")

    # First chat() call is the answer; its system prompt must carry the recalled fact.
    answer_prompt = seen[0]
    assert "allergic to peanuts" in answer_prompt
    assert "Aegis" in answer_prompt  # persona is present


def test_cross_session_recall(patched):
    root = str(patched / "session")

    # Session 1: tell the agent something, then it goes away.
    a1 = MemoryAgent(MemoryStore(root=root))
    a1.chat("Please call me Ada and remember I'm allergic to peanuts.")

    # Session 2: fresh process/agent, same memory dir, NO replay of history.
    a2 = MemoryAgent(MemoryStore(root=root))
    picked, prefs = a2.mem.recall("is there anything I can't eat?")

    assert any("allergic" in p["text"].lower() for p in picked)
    assert prefs.get("name", {}).get("value") == "ada"


def test_learn_survives_bad_extractor_json(monkeypatch, patched):
    # Extractor returns garbage -> learning must degrade gracefully, not crash.
    monkeypatch.setattr(qwen, "chat",
                        lambda messages, model=None, temperature=0.4: "not json at all")
    agent = MemoryAgent(MemoryStore(root=str(patched / "robust")))
    reply = agent.chat("hello there")  # must not raise
    assert reply == "not json at all"
    assert agent.mem.stats()["facts"] == 0


@pytest.mark.parametrize("payload", [
    '{"prefs": ["not", "a", "dict"]}',   # prefs is a list -> .items() would blow up
    '{"facts": [{"nested": 1}]}',        # a fact is a dict -> .strip() would blow up
    '{"episode": 123}',                  # episode is an int -> .strip() would blow up
    '["totally", "wrong", "shape"]',     # top-level JSON isn't even an object
])
def test_learn_survives_wellformed_json_with_bad_types(monkeypatch, patched, payload):
    # The extractor can return VALID JSON that still carries the wrong types. That
    # parses cleanly (so the earlier try/except doesn't catch it) but the apply loop
    # runs AFTER the reply is generated — a type error there must not crash the turn
    # and swallow an answer the user already earned.
    monkeypatch.setattr(qwen, "chat",
                        lambda messages, model=None, temperature=0.4: payload)
    agent = MemoryAgent(MemoryStore(root=str(patched / "badtypes")))

    reply = agent.chat("hello there")  # must not raise

    assert reply == payload            # the answer is returned intact
    # Nothing mis-typed was stored.
    assert agent.mem.stats()["facts"] == 0
    assert agent.mem.stats()["episodes"] == 0
    assert agent.mem.stats()["prefs"] == 0


def test_learn_keeps_valid_items_from_a_mixed_list(monkeypatch, patched):
    # A list mixing a bad-typed fact with a good one keeps the good one and drops
    # the bad one, rather than aborting the whole extraction on the first bad item.
    monkeypatch.setattr(
        qwen, "chat",
        lambda messages, model=None, temperature=0.4:
        '{"facts": [{"nested": 1}, "The user keeps bees"], "prefs": {"tone": "curt"}}')
    agent = MemoryAgent(MemoryStore(root=str(patched / "mixed")))

    agent.chat("hello there")  # must not raise

    assert any("keeps bees" in f["text"] for f in agent.mem.facts)
    assert len(agent.mem.facts) == 1                       # the dict was skipped
    assert agent.mem.prefs.get("tone", {}).get("value") == "curt"
