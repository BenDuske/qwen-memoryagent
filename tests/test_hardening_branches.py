"""Robustness/safety branches that the happy-path tests don't reach.

Three small-but-real guarantees:
  1. agent.chat() honors policy.screen's verdict: a BLOCKED input returns the
     refusal and the LLM/recall are NEVER touched (disallowed content must not
     reach Qwen Cloud). agent.py:34.
  2. memory.add_episode() ignores an empty/whitespace summary — no blank row,
     no wasted embedding call. memory.py:82.
  3. config._load_env_files() degrades to a no-op when a .env candidate is
     unreadable (OSError), rather than crashing import. config.py:30-31.
"""
import builtins

from memoryagent import qwen, config, policy
from memoryagent.memory import MemoryStore
from memoryagent.agent import MemoryAgent


def test_blocked_input_returns_refusal_without_touching_the_llm(monkeypatch, patched):
    """A screened-out message short-circuits: refusal out, qwen.chat never called."""
    monkeypatch.setattr(policy, "screen",
                        lambda text: (False, "minor_safety", "REFUSED-SENTINEL"))

    def _boom(*a, **k):
        raise AssertionError("qwen.chat must not be called for blocked input")

    monkeypatch.setattr(qwen, "chat", _boom)

    agent = MemoryAgent(MemoryStore(root=str(patched / "blocked")))
    reply = agent.chat("...anything...")

    assert reply == "REFUSED-SENTINEL"
    # Nothing was learned from a blocked turn.
    assert agent.mem.stats()["facts"] == 0
    assert agent.mem.stats()["episodes"] == 0


def test_add_episode_ignores_empty_summary(monkeypatch, store):
    """Whitespace-only summary is dropped before any store/embed work."""
    monkeypatch.setattr(qwen, "embed",
                        lambda *a, **k: (_ for _ in ()).throw(
                            AssertionError("embed must not run for an empty episode")))

    store.add_episode("   \n\t  ")

    assert store.stats()["episodes"] == 0


def test_load_env_files_survives_unreadable_candidate(monkeypatch):
    """An OSError opening a .env candidate is swallowed — import must not crash."""
    def _deny(*a, **k):
        raise OSError("permission denied")

    monkeypatch.setattr(builtins, "open", _deny)

    # Must not raise; it simply fills nothing.
    config._load_env_files()
