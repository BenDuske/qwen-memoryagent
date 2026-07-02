"""Fail-closed guarantees of the safety / consent / ethics layer.

Pins the degradation branches that must NEVER fail open: empty input, an unreadable
ethics file, a corrupt/stale consent record, and an interrupted first-run prompt.
Pure tests — no policy semantics are changed here. All keyless, no network.
"""
import json
import os

from memoryagent import policy


# --- screen(): empty / falsy input is allowed (line 68) --------------------------------------
def test_screen_empty_and_none_are_allowed():
    for val in ("", None):
        allowed, cat, msg = policy.screen(val)
        assert allowed is True and cat is None and msg is None


# --- load_ethics(): an unreadable file degrades to {} instead of raising (lines 99-100) ------
def test_load_ethics_unreadable_file_returns_empty(tmp_path, monkeypatch):
    # Point the ethics file at a DIRECTORY: os.path.exists() is True so it passes the guard,
    # but open() then raises (IsADirectoryError/PermissionError) -> except -> {}.
    d = tmp_path / "not-a-file"
    d.mkdir()
    monkeypatch.setenv("AEGIS_ETHICS_FILE", str(d))
    assert policy.load_ethics() == {}
    # and the preamble simply omits org context rather than blowing up
    assert policy.ethics_preamble() == ""


# --- has_consent(): a corrupt record is never read as consent (fail-closed, lines 146-147) ---
def test_has_consent_corrupt_record_is_false(tmp_path, monkeypatch):
    monkeypatch.setattr(policy.config, "MEMORY_DIR", str(tmp_path))
    monkeypatch.delenv("AEGIS_ASSUME_CONSENT", raising=False)
    p = policy._consent_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("{ this is not valid json ]")
    assert policy.has_consent() is False


def test_has_consent_stale_version_is_false(tmp_path, monkeypatch):
    # A well-formed record from an OLDER policy version must not count as current consent.
    monkeypatch.setattr(policy.config, "MEMORY_DIR", str(tmp_path))
    monkeypatch.delenv("AEGIS_ASSUME_CONSENT", raising=False)
    p = policy._consent_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump({"version": "1970-01-01", "agreed": True}, fh)
    assert policy.has_consent() is False


# --- ensure_consent(): short-circuits when consent already on file (line 176) ----------------
def test_ensure_consent_short_circuits_when_already_consented(monkeypatch):
    monkeypatch.setenv("AEGIS_ASSUME_CONSENT", "1")

    def _boom(_prompt=""):
        raise AssertionError("input_fn must not be called once consent exists")

    try:
        assert policy.ensure_consent(input_fn=_boom, output_fn=lambda *_: None) is True
    finally:
        monkeypatch.delenv("AEGIS_ASSUME_CONSENT", raising=False)


# --- ensure_consent(): an interrupted prompt neither grants nor records consent (179-181) ----
def test_ensure_consent_interrupted_prompt_declines(tmp_path, monkeypatch):
    monkeypatch.setattr(policy.config, "MEMORY_DIR", str(tmp_path))
    monkeypatch.delenv("AEGIS_ASSUME_CONSENT", raising=False)

    for exc in (EOFError, KeyboardInterrupt):
        seen = []

        def _raise(_prompt=""):
            raise exc

        assert policy.ensure_consent(input_fn=_raise, output_fn=lambda m="": seen.append(m)) is False
        # nothing was recorded, so the gate is still closed
        assert policy.has_consent() is False
        assert any("exiting" in m.lower() for m in seen)
