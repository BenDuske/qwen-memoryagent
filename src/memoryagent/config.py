"""Configuration — all via env (see .env.example)."""
import os

QWEN_BASE_URL = os.environ.get("QWEN_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1")
QWEN_API_KEY  = os.environ.get("QWEN_API_KEY") or os.environ.get("DASHSCOPE_API_KEY", "")
CHAT_MODEL    = os.environ.get("QWEN_CHAT_MODEL", "qwen3.7-plus")
EMBED_MODEL   = os.environ.get("QWEN_EMBED_MODEL", "text-embedding-v4")

MEMORY_DIR    = os.environ.get("MEMORY_DIR", os.path.expanduser("~/.aegis-memoryagent"))

# Recall is bounded: pack the highest-salience memories until the token budget is hit.
RECALL_TOKEN_BUDGET = int(os.environ.get("RECALL_TOKEN_BUDGET", "1200"))
RECALL_TOP_K        = int(os.environ.get("RECALL_TOP_K", "8"))
# Forgetting: episodic memories decay; below the floor they're pruned.
DECAY_HALFLIFE_DAYS = float(os.environ.get("DECAY_HALFLIFE_DAYS", "14"))
SALIENCE_FLOOR      = float(os.environ.get("SALIENCE_FLOOR", "0.12"))

PERSONA = os.environ.get(
    "PERSONA",
    "You are Aegis, a helpful assistant with persistent memory of this user. "
    "Use the recalled memory and preferences when relevant; never invent remembered facts.",
)
