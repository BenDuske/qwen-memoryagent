# Aegis MemoryAgent — © 2026 Ben Duske. Licensed under the MIT License (see LICENSE).
"""Deploy-critical contract: a misconfigured numeric env var must NOT brick import.

`config` parses its tuning knobs (RECALL_TOKEN_BUDGET / RECALL_TOP_K / DECAY_HALFLIFE_DAYS
/ SALIENCE_FLOOR) from the environment at IMPORT time. `os.environ.get(key, default)` only
returns the default when the key is ABSENT — a present-but-empty value (a `.env` line like
`RECALL_TOP_K=`, or an empty Docker/ECS env var) reaches int()/float() as "" and, before the
`_num_env` guard, raised `ValueError` at import, taking down EVERY entrypoint (demo, CLI, HTTP
service, container) with an opaque traceback before any code ran. These pin the graceful
degrade-to-default behavior so a bad env can't crash startup.
"""
import importlib

import pytest

from memoryagent import config


def _reload_with(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    importlib.reload(config)


@pytest.fixture(autouse=True)
def _restore_config():
    """Always restore the module to its env-free defaults so other tests see a clean config."""
    yield
    importlib.reload(config)


# --- the bug: empty value must degrade to the default, not crash import ----------------------

def test_empty_int_env_degrades_to_default(monkeypatch):
    _reload_with(monkeypatch, RECALL_TOP_K="", RECALL_TOKEN_BUDGET="")
    assert config.RECALL_TOP_K == 8
    assert config.RECALL_TOKEN_BUDGET == 1200


def test_empty_float_env_degrades_to_default(monkeypatch):
    _reload_with(monkeypatch, DECAY_HALFLIFE_DAYS="", SALIENCE_FLOOR="")
    assert config.DECAY_HALFLIFE_DAYS == 14.0
    assert config.SALIENCE_FLOOR == 0.12


def test_whitespace_and_nonnumeric_env_degrade_to_default(monkeypatch):
    # trailing inline junk / stray whitespace / words all fall back rather than raise
    _reload_with(
        monkeypatch,
        RECALL_TOKEN_BUDGET="1200 # tokens",
        RECALL_TOP_K="   ",
        DECAY_HALFLIFE_DAYS="fourteen",
        SALIENCE_FLOOR="0.12x",
    )
    assert config.RECALL_TOKEN_BUDGET == 1200
    assert config.RECALL_TOP_K == 8
    assert config.DECAY_HALFLIFE_DAYS == 14.0
    assert config.SALIENCE_FLOOR == 0.12


# --- valid overrides are still honored (the guard must not swallow good config) --------------

def test_valid_int_and_float_overrides_are_honored(monkeypatch):
    _reload_with(
        monkeypatch,
        RECALL_TOP_K="3",
        RECALL_TOKEN_BUDGET="500",
        DECAY_HALFLIFE_DAYS="7.5",
        SALIENCE_FLOOR="0.3",
    )
    assert config.RECALL_TOP_K == 3
    assert config.RECALL_TOKEN_BUDGET == 500
    assert config.DECAY_HALFLIFE_DAYS == 7.5
    assert config.SALIENCE_FLOOR == 0.3


def test_surrounding_whitespace_on_valid_value_is_tolerated(monkeypatch):
    _reload_with(monkeypatch, RECALL_TOP_K="  5  ")
    assert config.RECALL_TOP_K == 5


# --- absent keys fall back to the documented defaults ---------------------------------------

def test_absent_keys_use_defaults(monkeypatch):
    for k in ("RECALL_TOKEN_BUDGET", "RECALL_TOP_K", "DECAY_HALFLIFE_DAYS", "SALIENCE_FLOOR"):
        monkeypatch.delenv(k, raising=False)
    importlib.reload(config)
    assert config.RECALL_TOKEN_BUDGET == 1200
    assert config.RECALL_TOP_K == 8
    assert config.DECAY_HALFLIFE_DAYS == 14.0
    assert config.SALIENCE_FLOOR == 0.12
