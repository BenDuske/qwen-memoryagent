# Aegis MemoryAgent — © 2026 Ben Duske. Licensed under the MIT License (see LICENSE).
"""FastAPI service variant — the same MemoryAgent behind an HTTP API.

This is the deployable face of the agent (Alibaba Cloud Function Compute / ECS /
Container). It is a thin transport over the exact same memory engine the CLI uses:
recall → answer (Qwen Cloud) → extract → forget. Nothing about the memory logic
changes; only the entrypoint does.

Per-user isolation: each `user` gets its own MemoryStore rooted under MEMORY_DIR,
so cross-session recall is scoped to that user and survives process restarts
(mount MEMORY_DIR on a persistent volume — see DEPLOY.md).

Run locally:
    pip install -e ".[service]"
    uvicorn memoryagent.app:app --host 0.0.0.0 --port 8000
"""
import os
import re
import threading
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from . import config, policy
from .agent import MemoryAgent
from .memory import MemoryStore

app = FastAPI(
    title="Aegis MemoryAgent",
    version="0.1.0",
    description="Persistent-memory agent on Qwen Cloud (Hackathon Track 1).",
)

# One MemoryAgent per user, cached for the process lifetime. The store itself is
# the durable part — it lives on disk under MEMORY_DIR/<user>.
_AGENTS: dict[str, MemoryAgent] = {}
_SAFE_USER = re.compile(r"[^a-zA-Z0-9_.-]")
# FastAPI runs these sync handlers in a threadpool, so requests for the SAME new
# user can race the get-or-create below. Without this guard two threads both pass
# the `not in` check and each builds a MemoryStore over the same on-disk root;
# their independent in-memory lists then full-file-rewrite over each other =
# lost writes. The lock serializes only agent creation (a fast, one-time cost per
# user); steady-state requests hit the cache and never contend.
_AGENTS_LOCK = threading.Lock()


def _user_root(user: str) -> str:
    safe = _SAFE_USER.sub("_", user)
    # `_SAFE_USER` neutralizes path separators but INTENTIONALLY allows dots (real
    # ids like "a.b" are valid), so a name that is empty or ALL dots — "", ".", ".."
    # — survives and then `os.path.join(MEMORY_DIR, safe)` resolves to the MEMORY_DIR
    # root itself (".") or its PARENT (".."), escaping the per-user isolation root and,
    # in a container, the mounted MEMORY_DIR volume (`user=".."` → writes land in /data,
    # not /data/memory). `body.user` is free-form client input on /chat, so collapse any
    # such name to the shared default bucket. Any id with ≥1 non-dot char is unchanged.
    if not safe.strip("."):
        safe = "default"
    return os.path.join(config.MEMORY_DIR, safe)


def _agent_for(user: str) -> MemoryAgent:
    agent = _AGENTS.get(user)
    if agent is not None:
        return agent
    with _AGENTS_LOCK:
        # Double-checked: another thread may have created it while we waited.
        agent = _AGENTS.get(user)
        if agent is None:
            agent = MemoryAgent(MemoryStore(root=_user_root(user)))
            _AGENTS[user] = agent
        return agent


class ChatIn(BaseModel):
    user: str = Field("default", description="Stable user id; scopes the memory.")
    text: str = Field(..., min_length=1, description="The user's message.")


class ChatOut(BaseModel):
    reply: str
    stats: dict


class RecallOut(BaseModel):
    recalled: list[dict]
    prefs: dict


@app.get("/healthz")
def healthz():
    # Operators of a hosted deployment accept the Terms/AUP on their users' behalf and must
    # surface them downstream (see CONSENT.md / docs/legal/). The safety preamble + input
    # screen apply on every /chat regardless.
    return {"ok": True, "memory_dir": config.MEMORY_DIR, "chat_model": config.CHAT_MODEL,
            "policy_version": policy.POLICY_VERSION}


@app.post("/chat", response_model=ChatOut)
def chat(body: ChatIn):
    agent = _agent_for(body.user)
    try:
        reply = agent.chat(body.text)
    except Exception as e:  # surface Qwen Cloud / config errors as 502
        raise HTTPException(status_code=502, detail=str(e))
    return ChatOut(reply=reply, stats=agent.mem.stats())


@app.get("/memory/{user}/stats")
def stats(user: str):
    return _agent_for(user).mem.stats()


@app.get("/memory/{user}/recall", response_model=RecallOut)
def recall(user: str, q: str, budget: Optional[int] = None, top_k: Optional[int] = None):
    """Inspect bounded recall directly — what *would* be injected for a query,
    and at what token cost. This is the Track-1 'recall within a limited context
    window' guarantee, made observable."""
    try:
        picked, prefs = _agent_for(user).mem.recall(q, token_budget=budget, top_k=top_k)
    except Exception as e:  # embedding the query hits Qwen Cloud — surface as 502, not a bare 500
        raise HTTPException(status_code=502, detail=str(e))
    slim = [{"text": p["text"], "ts": p["ts"], "importance": p.get("importance")}
            for p in picked]
    return RecallOut(recalled=slim, prefs=prefs)


@app.post("/memory/{user}/forget")
def forget(user: str):
    dropped = _agent_for(user).mem.forget()
    return {"dropped": dropped, "stats": _agent_for(user).mem.stats()}
