"""Test fixtures — run the whole agent WITHOUT a Qwen Cloud key.

We monkeypatch the only two functions that touch the network (`qwen.embed`,
`qwen.chat`) with deterministic fakes. The fake embedding is a stable hashing
bag-of-words vector, so cosine similarity is *real*: texts that share words
score higher, which is exactly what the recall ranking needs to be testable.
"""
import hashlib
import re

import pytest

from memoryagent import qwen, config
from memoryagent.memory import MemoryStore
from memoryagent.agent import MemoryAgent

_DIM = 64
_TOKEN = re.compile(r"[a-z0-9]+")


def _stable_hash(token: str) -> int:
    # Python's str hash is salted per process; use a stable digest instead.
    return int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)


def fake_embed(texts):
    if isinstance(texts, str):
        texts = [texts]
    out = []
    for t in texts:
        vec = [0.0] * _DIM
        for tok in _TOKEN.findall(t.lower()):
            vec[_stable_hash(tok) % _DIM] += 1.0
        out.append(vec)
    return out


def make_fake_chat(record=None):
    """A chat stub. When handed the memory-extraction system prompt it returns
    STRICT JSON the agent can parse; otherwise it echoes a canned reply.
    Pass `record` (a list) to capture the system prompts it was called with."""
    def fake_chat(messages, model=None, temperature=0.4):
        system = messages[0]["content"] if messages else ""
        if record is not None:
            record.append(system)
        if "extract durable memory" in system.lower():
            user = messages[1]["content"] if len(messages) > 1 else ""
            facts, prefs = [], {}
            # Deterministic, content-driven extraction so the loop is testable.
            if "allerg" in user.lower() or "peanut" in user.lower():
                facts.append("User is allergic to peanuts")
            if "call me" in user.lower():
                m = re.search(r"call me (\w+)", user.lower())
                if m:
                    prefs["name"] = m.group(1)
            return (
                '{"facts": %s, "prefs": %s, "episode": "exchange summary"}'
                % (_json_list(facts), _json_obj(prefs))
            )
        return "ok (stubbed reply)"
    return fake_chat


def _json_list(items):
    import json
    return json.dumps(items)


def _json_obj(obj):
    import json
    return json.dumps(obj)


@pytest.fixture
def patched(monkeypatch, tmp_path):
    """Patch the network calls and point MEMORY_DIR at a temp dir."""
    monkeypatch.setattr(qwen, "embed", fake_embed)
    monkeypatch.setattr(qwen, "chat", make_fake_chat())
    monkeypatch.setattr(config, "MEMORY_DIR", str(tmp_path / "mem"))
    return tmp_path


@pytest.fixture
def store(patched):
    return MemoryStore(root=str(patched / "store"))


@pytest.fixture
def agent(patched):
    return MemoryAgent(MemoryStore(root=str(patched / "agentmem")))
