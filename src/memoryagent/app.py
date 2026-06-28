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


def _user_root(user: str) -> str:
    safe = _SAFE_USER.sub("_", user) or "default"
    return os.path.join(config.MEMORY_DIR, safe)


def _agent_for(user: str) -> MemoryAgent:
    if user not in _AGENTS:
        _AGENTS[user] = MemoryAgent(MemoryStore(root=_user_root(user)))
    return _AGENTS[user]


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
def recall(user: str, q: str, budget: int | None = None, top_k: int | None = None):
    """Inspect bounded recall directly — what *would* be injected for a query,
    and at what token cost. This is the Track-1 'recall within a limited context
    window' guarantee, made observable."""
    picked, prefs = _agent_for(user).mem.recall(q, token_budget=budget, top_k=top_k)
    slim = [{"text": p["text"], "ts": p["ts"], "importance": p.get("importance")}
            for p in picked]
    return RecallOut(recalled=slim, prefs=prefs)


@app.post("/memory/{user}/forget")
def forget(user: str):
    dropped = _agent_for(user).mem.forget()
    return {"dropped": dropped, "stats": _agent_for(user).mem.stats()}
