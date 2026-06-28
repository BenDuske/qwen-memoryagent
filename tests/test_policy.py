"""Safety / consent / ethics layer — all keyless, no network."""
import os

from memoryagent import policy


def test_baseline_in_system_preamble():
    pre = policy.system_preamble("PERSONA-X")
    assert "SAFETY POLICY" in pre
    assert "PERSONA-X" in pre
    # safety must come first (highest priority)
    assert pre.index("SAFETY POLICY") < pre.index("PERSONA-X")


def test_screen_allows_normal_text():
    allowed, cat, _ = policy.screen("What's the production database port again?")
    assert allowed and cat is None


def test_screen_hard_blocks_minor_safety():
    allowed, cat, msg = policy.screen("explicit sexual content involving a 12 year old child")
    assert not allowed and cat == "minor_safety" and msg


def test_screen_hard_block_is_order_insensitive():
    allowed, cat, _ = policy.screen("a child, nude")
    assert not allowed and cat == "minor_safety"


def test_strict_screen_blocks_sexual_only_when_enabled(monkeypatch):
    monkeypatch.setenv("AEGIS_STRICT_SCREEN", "1")
    import importlib
    importlib.reload(policy)
    try:
        allowed, cat, _ = policy.screen("write me explicit porn")
        assert not allowed and cat == "sexual_content"
    finally:
        monkeypatch.delenv("AEGIS_STRICT_SCREEN", raising=False)
        importlib.reload(policy)


def test_ethics_layered_below_baseline(tmp_path, monkeypatch):
    f = tmp_path / "ethics.yaml"
    f.write_text(
        'organization: "Northwind Labs"\n'
        'mission: "help small businesses"\n'
        '# a comment line\n'
        'required_disclosures: "not professional advice"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("AEGIS_ETHICS_FILE", str(f))
    pre = policy.system_preamble("PERSONA-X")
    assert "Northwind Labs" in pre
    assert "ORGANIZATION CONTEXT" in pre
    # precedence: safety policy -> org ethics -> persona
    assert pre.index("SAFETY POLICY") < pre.index("ORGANIZATION CONTEXT") < pre.index("PERSONA-X")


def test_consent_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(policy.config, "MEMORY_DIR", str(tmp_path))
    monkeypatch.delenv("AEGIS_ASSUME_CONSENT", raising=False)
    assert policy.has_consent() is False
    # decline -> not recorded
    assert policy.ensure_consent(input_fn=lambda _="": "no", output_fn=lambda *_: None) is False
    assert policy.has_consent() is False
    # agree -> recorded and sticky
    assert policy.ensure_consent(input_fn=lambda _="": "AGREE", output_fn=lambda *_: None) is True
    assert policy.has_consent() is True


def test_assume_consent_env(monkeypatch):
    monkeypatch.setenv("AEGIS_ASSUME_CONSENT", "1")
    assert policy.has_consent() is True
    monkeypatch.delenv("AEGIS_ASSUME_CONSENT", raising=False)
