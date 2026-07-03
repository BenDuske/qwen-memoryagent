# Aegis MemoryAgent — © 2026 Ben Duske. Licensed under the MIT License (see LICENSE).
"""Regression: MemoryStore must not leak file handles.

`_load_jsonl`, `_load_prefs` and `_save_prefs` used to call `open(...)` without a
`with`/close, leaking a handle per load/save until GC reaped it (surfaced as
`ResourceWarning: unclosed file` under `-W error::ResourceWarning`). `_save_jsonl`
was already correct. These tests pin the fix two ways:

1. deterministic — wrap `builtins.open` and assert every handle the store opens is
   closed by the time the operation returns (no dependence on GC timing);
2. belt-and-braces — drive a full write+reload round-trip with ResourceWarning
   promoted to an error, proving the suite stays clean.
"""
import builtins
import warnings

import pytest

from memoryagent.memory import MemoryStore


class _TrackedFile:
    """Proxy that records close() so the test can prove the handle was released."""
    def __init__(self, fh, registry):
        self._fh = fh
        self._registry = registry
        registry.append(self)
        self.closed_seen = False

    def close(self):
        self.closed_seen = True
        return self._fh.close()

    def __iter__(self):
        return iter(self._fh)

    def __enter__(self):
        self._fh.__enter__()
        return self

    def __exit__(self, *a):
        self.close()
        return self._fh.__exit__(*a)

    def __getattr__(self, name):
        return getattr(self._fh, name)


@pytest.fixture
def track_open(monkeypatch):
    opened = []
    real_open = builtins.open

    def tracking_open(*a, **k):
        return _TrackedFile(real_open(*a, **k), opened)

    monkeypatch.setattr(builtins, "open", tracking_open)
    return opened


def _all_closed(opened):
    return [f for f in opened if not (f.closed_seen or f._fh.closed)]


def test_writes_and_loads_close_every_handle(patched, track_open):
    root = str(patched / "leakstore")

    s = MemoryStore(root=root)          # _load_jsonl x2 + _load_prefs (missing -> skip)
    s.add_fact("User is allergic to peanuts")   # _save_jsonl
    s.add_episode("first exchange summary")     # _save_jsonl
    s.set_pref("name", "Ben")                   # _save_prefs

    # Reopen so every load path (incl. _load_prefs with an existing file) runs.
    MemoryStore(root=root)

    leaked = _all_closed(track_open)
    assert not leaked, f"{len(leaked)} file handle(s) left open by MemoryStore"


def test_roundtrip_clean_under_resourcewarning_as_error(patched):
    root = str(patched / "warnstore")
    with warnings.catch_warnings():
        warnings.simplefilter("error", ResourceWarning)
        s = MemoryStore(root=root)
        s.add_fact("durable fact about the user")
        s.add_episode("an episode to persist")
        s.set_pref("tone", "blunt")
        reloaded = MemoryStore(root=root)
        assert reloaded.stats()["facts"] == 1
        assert reloaded.prefs["tone"]["value"] == "blunt"
