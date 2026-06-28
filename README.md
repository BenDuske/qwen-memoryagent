# Aegis MemoryAgent — Qwen Cloud Hackathon (Track 1: MemoryAgent)

An AI agent with **persistent, evolving memory** built on **Qwen Cloud**. It accumulates
experience across sessions, learns the user's preferences and facts, **forgets** what goes
stale, and **recalls only the most salient memories within a bounded context window** — the
exact brief of Track 1.

> Submission to the *Global AI Hackathon Series with Qwen Cloud*. Backend runs on Alibaba Cloud
> (Model Studio / DashScope, OpenAI-compatible Qwen endpoints). © Digital Real-Estate Frontier, LLC.

## Why this is a MemoryAgent (not a chatbot with a log)

Most "memory" demos paste the whole history into the prompt. That breaks the moment history
exceeds the context window. This agent treats memory as a **managed store with a salience
budget**, on three layers that update at very different costs:

| Layer | Holds | Update cost | Recall |
|------|-------|-------------|--------|
| **Episodic** | timestamped interaction summaries | cheap | semantic + recency-decayed |
| **Facts** | durable knowledge about the user/world | cheap | semantic top-k |
| **Preferences** | how the user wants to be served | trivial | always injected (small) |

Every turn: **retrieve** the most salient memories that fit a token budget → **answer** with
Qwen → **extract** new facts/prefs/episodes → **forget** low-salience, stale memories.

### The three hard things Track 1 asks for
1. **Efficient storage & retrieval** — append-only JSONL + a vector index; retrieval is
   `salience = similarity × recency_decay × importance`, not raw recency.
2. **Timely forgetting** — episodic memories decay; below a salience floor they're pruned
   (or compacted into a fact). Preferences are last-write-wins so corrections overwrite, never
   pile up.
3. **Recall within a limited context window** — a hard **token budget** packs the highest-salience
   memories first and stops; nothing overflows the window no matter how long history grows.

## Architecture

```
user ──▶ MemoryAgent
            │  1. recall(query, budget)  ── semantic + recency over episodic/facts (+ all prefs)
            │  2. build bounded prompt    ── persona + prefs + recalled facts + recent episodes
            │  3. Qwen Cloud chat         ── DashScope OpenAI-compatible (qwen-plus/qwen-max)
            │  4. extract memories        ── facts / prefs / episode from the exchange
            │  5. consolidate + forget    ── decay, prune, compact
            ▼
        memory store (JSONL + vector index)  ── embeddings via Qwen text-embedding-v3
```

## Run

```bash
cp .env.example .env          # add your Qwen Cloud (DashScope) API key
pip install -r requirements.txt
python -m memoryagent.cli     # interactive; memory persists across runs (prove cross-session recall)
```

Backend is **100% Qwen Cloud**: chat + embeddings both call DashScope's OpenAI-compatible
endpoint. See `DEPLOY.md` for the Alibaba Cloud (Function Compute / ECS) deployment proof.

## Repo layout

```
src/memoryagent/
  config.py     env + tunables (budget, decay, salience floor)
  qwen.py       Qwen Cloud client (chat + embed, OpenAI-compatible)
  memory.py     the 3-layer store: recall / extract / forget  ← the heart
  agent.py      the turn loop
  cli.py        cross-session REPL demo
Dockerfile      Alibaba Cloud deployable
DEPLOY.md       Alibaba Cloud deployment proof
docs/architecture.svg   system diagram (for the submission)
```

## Hackathon checklist
- [x] Built on Qwen models via Qwen Cloud
- [x] Open-source repo + license (MIT)
- [ ] Proof of Alibaba Cloud deployment (`DEPLOY.md` + Dockerfile)
- [ ] Architecture diagram (`docs/architecture.svg`)
- [ ] < 3-min demo video (script in `docs/demo-script.md`)
- [ ] (bonus) build-journey blog post

License: MIT (see `LICENSE`). Copyright © 2026 Digital Real-Estate Frontier, LLC.
