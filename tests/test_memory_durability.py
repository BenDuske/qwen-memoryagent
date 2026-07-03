# Aegis MemoryAgent — © 2026 Ben Duske. Licensed under the MIT License (see LICENSE).
"""Durability: a crash during a memory write must never lose the whole store.

`_save_jsonl`/`_save_prefs` used to rewrite the file in place with mode "w", so a
crash/power-loss mid-write left a *torn* file; `_load_jsonl`/`_load_prefs` then did
an unguarded `json.loads`, so a single torn line raised on the next startup and took
down ALL of memory. These tests pin the two-part fix:

1. ROOT CAUSE — writes are atomic (temp file + os.replace), so an interrupted save
   leaves the previous good file intact, never a half-written one.
2. DEFENSE-IN-DEPTH — the loaders tolerate a pre-existing corrupt record: a torn
   JSONL line is skipped (the rest survive) and a corrupt prefs.json degrades to {}.
"""
import json

import pytest

from memoryagent.memory import MemoryStore


def test_torn_jsonl_line_does_not_nuke_the_store(patched):
    root = str(patched / "torn")
    s = MemoryStore(root=root)
    s.add_fact("User is allergic to peanuts")
    s.add_fact("User lives in Lubbock, TX")

    # Simulate a blank line (harmless) then a crash-torn last record.
    with open(s._p("facts.jsonl"), "a", encoding="utf-8") as f:
        f.write("\n")  # stray blank line must be skipped, not fatal
        f.write('{"text": "half-written record", "emb": [0.1, 0.2')  # no newline, no close brace

    reloaded = MemoryStore(root=root)
    texts = {fct["text"] for fct in reloaded.facts}
    # Both valid facts survive; the torn record is dropped, not fatal.
    assert texts == {"User is allergic to peanuts", "User lives in Lubbock, TX"}


def test_corrupt_prefs_degrades_to_empty(patched):
    root = str(patched / "badprefs")
    s = MemoryStore(root=root)
    s.set_pref("tone", "blunt")

    with open(s._p("prefs.json"), "w", encoding="utf-8") as f:
        f.write("{ this is not valid json ")

    reloaded = MemoryStore(root=root)          # must not raise
    assert reloaded.prefs == {}


def test_saves_are_atomic_no_partial_file_on_crash(patched, monkeypatch):
    """If rendering blows up mid-write, os.replace never runs, so the live file
    is either the prior good version or (first write) absent — never torn."""
    root = str(patched / "atomic")
    s = MemoryStore(root=root)
    s.add_fact("first durable fact")           # writes a valid facts.jsonl

    # Force the *next* render to fail partway by making json.dumps raise.
    import memoryagent.memory as mem

    real_dumps = mem.json.dumps
    calls = {"n": 0}

    def exploding_dumps(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated crash mid-render")
        return real_dumps(*a, **k)

    monkeypatch.setattr(mem.json, "dumps", exploding_dumps)
    with pytest.raises(RuntimeError):
        s.add_fact("second fact that fails to persist")
    monkeypatch.undo()

    # The on-disk file is still the intact single-fact version; no temp leftover
    # is ever read (only the final path is loaded), and it is not torn.
    reloaded = MemoryStore(root=root)
    assert [f["text"] for f in reloaded.facts] == ["first durable fact"]


def test_atomic_write_leaves_no_stray_tmp_after_success(patched):
    root = str(patched / "notmp")
    s = MemoryStore(root=root)
    s.add_fact("a fact")
    s.set_pref("name", "Ben")
    import os

    leftovers = [n for n in os.listdir(root) if n.endswith(".tmp")]
    assert leftovers == []


def test_roundtrip_still_correct_after_atomic_change(patched):
    """Behaviour is unchanged: normal write+reload preserves facts/prefs exactly."""
    root = str(patched / "roundtrip")
    s = MemoryStore(root=root)
    s.add_fact("durable fact")
    s.add_episode("an episode")
    s.set_pref("tone", "blunt")

    reloaded = MemoryStore(root=root)
    assert reloaded.stats()["facts"] == 1
    assert reloaded.stats()["episodes"] == 1
    assert reloaded.prefs["tone"]["value"] == "blunt"
    # And the persisted JSONL is genuinely one-object-per-line valid JSON.
    with open(reloaded._p("facts.jsonl"), encoding="utf-8") as f:
        for line in f:
            json.loads(line)
