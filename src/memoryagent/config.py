# Aegis MemoryAgent — © 2026 Ben Duske. Licensed under the MIT License (see LICENSE).
"""Configuration — all via env (see .env.example).

Env is loaded from the process environment first, then (for any keys not already set) from a
local `.env` at the repo root — so `cp .env.example .env` works exactly as the README documents,
with no extra dependency. An optional OpenClaw credentials file is also honored as a fallback.
"""
import os


def _load_env_files() -> None:
    """Fill os.environ from .env files for keys not already set (no override, no dependency)."""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, "..", "..", ".env"),                 # repo-root .env (documented path)
        os.path.expanduser("~/.openclaw/credentials/qwen.env"),  # optional local credentials fallback
    ]
    for path in candidates:
        try:
            with open(path, encoding="utf-8") as fh:
                for raw in fh:
                    line = raw.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if key and key not in os.environ:
                        os.environ[key] = val
        except OSError:
            pass


_load_env_files()


def _num_env(key: str, default, cast):
    """Parse a numeric env var, degrading to `default` on empty/whitespace/invalid.

    os.environ.get(key, fallback) only returns the fallback when the key is ABSENT, so a
    present-but-empty value (e.g. a `.env` line `RECALL_TOP_K=`) would reach int()/float()
    as "" and raise at IMPORT time — bricking the whole package (demo, CLI, HTTP service,
    Docker container) before any code runs. Any tuning knob that can't be parsed falls back
    to its documented default instead, so a misconfigured env can't take the app down.
    """
    raw = os.environ.get(key)
    raw = raw.strip() if isinstance(raw, str) else ""
    if not raw:
        return default
    try:
        return cast(raw)
    except (ValueError, TypeError):
        return default


QWEN_BASE_URL = os.environ.get("QWEN_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1")
QWEN_API_KEY  = os.environ.get("QWEN_API_KEY") or os.environ.get("DASHSCOPE_API_KEY", "")
CHAT_MODEL    = os.environ.get("QWEN_CHAT_MODEL", "qwen3.7-plus")
EMBED_MODEL   = os.environ.get("QWEN_EMBED_MODEL", "text-embedding-v4")

MEMORY_DIR    = os.environ.get("MEMORY_DIR", os.path.expanduser("~/.aegis-memoryagent"))

# Recall is bounded: pack the highest-salience memories until the token budget is hit.
RECALL_TOKEN_BUDGET = _num_env("RECALL_TOKEN_BUDGET", 1200, int)
RECALL_TOP_K        = _num_env("RECALL_TOP_K", 8, int)
# Forgetting: episodic memories decay; below the floor they're pruned.
DECAY_HALFLIFE_DAYS = _num_env("DECAY_HALFLIFE_DAYS", 14.0, float)
SALIENCE_FLOOR      = _num_env("SALIENCE_FLOOR", 0.12, float)

PERSONA = os.environ.get(
    "PERSONA",
    "You are Aegis, a helpful assistant with persistent memory of this user. "
    "Use the recalled memory and preferences when relevant; never invent remembered facts.",
)
