"""CLI REPL tests — the interactive `memoryagent.cli.main()` entrypoint.

`cli.py` is the human-facing face of the same memory engine the service uses,
and previously had ZERO direct coverage (the REPL loop, the consent gate, the
empty-line skip, the per-turn error guard, and the clean-exit path were all
untested). These tests run WITHOUT a Qwen Cloud key — the network calls are the
conftest fakes and MEMORY_DIR is a temp dir (`patched` fixture) — and drive the
loop by monkeypatching `builtins.input` with a scripted sequence, so no real
stdin is touched. Pure behavioural pinning: no CLI semantics change.
"""
import builtins

import pytest

from memoryagent import cli, policy


def _scripted_input(monkeypatch, items):
    """Feed main()'s input() from a list. A list entry that is an Exception
    (class or instance) is RAISED instead of returned — that's how we simulate
    Ctrl-D (EOFError) / Ctrl-C (KeyboardInterrupt) ending the session."""
    seq = iter(items)

    def fake_input(prompt=""):
        try:
            nxt = next(seq)
        except StopIteration:  # safety net: never hang the test on real stdin
            raise EOFError
        if isinstance(nxt, BaseException) or (
            isinstance(nxt, type) and issubclass(nxt, BaseException)
        ):
            raise nxt
        return nxt

    monkeypatch.setattr(builtins, "input", fake_input)


def test_consent_declined_returns_before_any_prompt(patched, monkeypatch, capsys):
    monkeypatch.setattr(policy, "ensure_consent", lambda: False)
    # If main() reached the loop it would call input(); make that a hard failure.
    monkeypatch.setattr(builtins, "input", lambda *a: pytest.fail("prompted despite declined consent"))

    cli.main()

    out = capsys.readouterr().out
    assert "MemoryAgent" not in out  # never printed the banner
    assert out.strip() == ""


def test_happy_path_banner_reply_and_clean_exit(patched, monkeypatch, capsys):
    monkeypatch.setattr(policy, "ensure_consent", lambda: True)
    # "" is skipped (empty-line branch), then a real turn, then Ctrl-D exits.
    _scripted_input(monkeypatch, ["", "hello there", EOFError])

    cli.main()

    out = capsys.readouterr().out
    assert "Aegis MemoryAgent" in out                 # banner
    assert "facts" in out and "episodes" in out       # loaded-stats line
    assert "aegis> ok (stubbed reply)" in out         # the stubbed chat reply
    assert "Memory saved. Bye." in out                # clean-exit message


def test_keyboard_interrupt_exits_cleanly(patched, monkeypatch, capsys):
    monkeypatch.setattr(policy, "ensure_consent", lambda: True)
    _scripted_input(monkeypatch, [KeyboardInterrupt])

    cli.main()

    assert "Memory saved. Bye." in capsys.readouterr().out


def test_per_turn_error_is_caught_and_loop_survives(patched, monkeypatch, capsys):
    monkeypatch.setattr(policy, "ensure_consent", lambda: True)

    class Boom(MemoryAgentStub):
        def chat(self, text):
            raise RuntimeError("qwen exploded")

    # Swap in a stub agent whose chat() raises, so we hit the `except` guard
    # WITHOUT depending on how the real engine might fail.
    monkeypatch.setattr(cli, "MemoryAgent", Boom)
    _scripted_input(monkeypatch, ["trigger the error", EOFError])

    cli.main()

    out = capsys.readouterr().out
    assert "[error] qwen exploded" in out       # error surfaced, not raised
    assert "Memory saved. Bye." in out          # loop continued to the next turn


class MemoryAgentStub:
    """Minimal stand-in for MemoryAgent: enough for cli.main()'s banner + loop."""

    class _Mem:
        def stats(self):
            return {"facts": 0, "episodes": 0, "prefs": 0, "dir": "<stub>"}

    def __init__(self, *a, **k):
        self.mem = self._Mem()

    def chat(self, text):
        return "stub reply"
