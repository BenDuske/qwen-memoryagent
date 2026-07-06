# Aegis MemoryAgent — © 2026 Ben Duske. Licensed under the MIT License (see LICENSE).
"""Deploy-critical contract: per-user memory stores stay rooted UNDER `MEMORY_DIR`.

Two guarantees are pinned here that the rest of the suite bypasses (every other test
`monkeypatch.setattr(config, "MEMORY_DIR", ...)`, so it never exercises the env read
nor the `_user_root` rooting/traversal logic):

  1. ENV BINDING — `config.MEMORY_DIR` is read from the `MEMORY_DIR` environment
     variable. This is the exact contract the Dockerfile (`ENV MEMORY_DIR=/data/memory`)
     and DEPLOY.md ("mount this on a persistent volume") depend on: rename the env var
     or hardcode a default and cross-restart persistence silently dies with the whole
     suite still green.

  2. ISOLATION / NO-ESCAPE — every user's store roots strictly under `MEMORY_DIR`.
     `_SAFE_USER` allows dots (real ids like "a.b"), so a crafted all-dot username
     ("." / "..") would otherwise `os.path.join` to the root itself or its PARENT,
     escaping per-user isolation and, in a container, the mounted `MEMORY_DIR` volume.
     `body.user` is free-form client input on /chat, so this is attacker-reachable.
"""
import importlib
import os

import pytest

pytest.importorskip("fastapi", reason="install the 'service' extra to run app tests")

from memoryagent import app, config  # noqa: E402


# --- 1. ENV BINDING: MEMORY_DIR comes from the environment --------------------

def test_memory_dir_read_from_env(monkeypatch):
    """config.MEMORY_DIR reflects the MEMORY_DIR env var (Dockerfile ENV contract)."""
    monkeypatch.setenv("MEMORY_DIR", "/mnt/persistent-volume")
    try:
        importlib.reload(config)
        # Set in os.environ, so _load_env_files() (no-override) must not clobber it.
        assert config.MEMORY_DIR == "/mnt/persistent-volume"
    finally:
        monkeypatch.undo()          # drop the env var...
        importlib.reload(config)    # ...and restore the module to its env-free default.


# --- 2. ISOLATION: _user_root never escapes MEMORY_DIR ------------------------

@pytest.fixture
def rooted(monkeypatch, tmp_path):
    """Point MEMORY_DIR at a temp dir and hand back its normalized absolute path."""
    root = tmp_path / "mem"
    monkeypatch.setattr(config, "MEMORY_DIR", str(root))
    return os.path.normpath(str(root))


def _inside(path: str, root: str) -> bool:
    """True iff `path` is `root` or a proper descendant of it (no `..` escape)."""
    root = os.path.normpath(root)
    path = os.path.normpath(path)
    return path == root or path.startswith(root + os.sep)


def test_normal_user_roots_under_memory_dir(rooted):
    r = app._user_root("alice")
    assert os.path.normpath(r) == os.path.join(rooted, "alice")
    assert _inside(r, rooted)


def test_dotted_but_real_user_is_untouched(rooted):
    # A dot inside a real id is a legitimate path component, NOT traversal.
    for user in ("a.b", "user.1", "a..b", "..z", "z.."):
        r = app._user_root(user)
        assert _inside(r, rooted), f"{user!r} escaped root -> {r}"
        # os.path.normpath must not collapse it back to (or above) the root.
        assert os.path.normpath(r) != rooted


@pytest.mark.parametrize("user", ["", ".", "..", "...", "/", "../..", "a/../../b", "..\\.."])
def test_traversal_and_empty_names_collapse_to_default(rooted, user):
    """Empty / all-dot / separator-laden names resolve to the shared default bucket,
    never to MEMORY_DIR itself or its parent."""
    r = app._user_root(user)
    assert _inside(r, rooted), f"{user!r} escaped isolation root -> {r}"
    # The dangerous cases ("", ".", "..") must land in the explicit default bucket.
    if user in ("", ".", "..", "..."):
        assert os.path.normpath(r) == os.path.join(rooted, "default")


def test_parent_escape_is_blocked(rooted):
    """Regression: `user=".."` must NOT root the store at MEMORY_DIR's parent."""
    parent = os.path.dirname(rooted)
    r = os.path.normpath(app._user_root(".."))
    assert r != parent
    assert r != rooted
    assert _inside(r, rooted)
