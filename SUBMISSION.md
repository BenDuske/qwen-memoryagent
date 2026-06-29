# Submission — Aegis MemoryAgent

**Hackathon:** Global AI Hackathon Series with Qwen Cloud
**Track:** 1 — MemoryAgent
**Repo:** https://github.com/BenDuske/qwen-memoryagent (MIT)
**Built on:** Qwen Cloud — Alibaba Cloud Model Studio / DashScope (OpenAI-compatible endpoints)
**Models:** `qwen3.7-plus` (chat) · `text-embedding-v4` (retrieval)

## One line

An AI agent with persistent, evolving memory that accumulates experience across sessions,
forgets what goes stale, and recalls **only the most salient memories within a bounded token
budget** — so it never overflows the context window no matter how long history grows.

## How it meets Track 1

Track 1 asks for three hard things. Each maps to real code and is exercised by the keyless
test suite (no API key required — `qwen.embed`/`qwen.chat` are monkeypatched in tests).

| Track 1 requirement | How we do it | Where |
|---|---|---|
| **Efficient storage & retrieval** | Append-only JSONL + vector index; retrieval ranks by `salience = similarity × recency_decay × importance`, not raw recency | `src/memoryagent/memory.py` · `tests/test_memory.py` |
| **Timely forgetting** | Episodic memories decay; below a salience floor they're pruned or compacted into a fact. Preferences are last-write-wins, so corrections overwrite instead of piling up | `memory.py` (consolidate/forget) · `tests/test_memory.py` |
| **Recall within a limited context window** | A hard token budget packs highest-salience memories first and stops; nothing overflows the window | `memory.py` (bounded recall) · `tests/test_memory.py::bounded budget` |

## Why it's a MemoryAgent, not a chatbot with a log

Most "memory" demos replay the whole transcript into the prompt — that breaks the instant
history exceeds the context window. This agent treats memory as a **managed store with a
salience budget** across three layers (episodic / facts / preferences) that update at very
different costs. Every turn: **recall** (bounded) → **answer** (Qwen) → **extract** new
memories → **consolidate + forget**.

## Measured result

`eval.py` pits the real salience engine against naive most-recent-first packing under a tight
token budget, over many scenarios:

- **Salience budget: 8/8** target memories recalled
- **Naive recency: 0/8**

The salience ranking is the difference between recalling the *relevant* memory and recalling
the *latest* one. Run it keyless: `python eval.py`.

## Proof it runs on Qwen Cloud

A live cross-session run against `qwen3.7-plus` + `text-embedding-v4` is captured in
[`docs/sample-run.md`](docs/sample-run.md): Session 2 is a **brand-new process over the same
on-disk store with no replayed history**, yet it recalls what Session 1 taught it. That is the
Track-1 point — recall from a managed store, not a giant replayed transcript.

This is **reproducible, not a one-off capture**: an independent second run on a later date
([`docs/transcripts/live-cross-session-demo.md`](docs/transcripts/live-cross-session-demo.md))
shows the same cross-session recall against the live endpoint.

## Deploy (Alibaba Cloud)

Runtime is **stdlib-only** for chat + embeddings (over `urllib`), so the container is tiny and
cold-starts fast. The HTTP face is FastAPI (`memoryagent.app:app`); the same engine also runs
as an interactive CLI. The one thing that must persist is `MEMORY_DIR` (the cross-session
store) — mount it on a persistent volume. Full steps in [`DEPLOY.md`](DEPLOY.md).

## Run it yourself

```bash
# keyless reproduce in one command (install + 26 tests + evaluation, no API key)
make verify

# …or the same steps by hand:
pip install -r requirements.txt
python -m pytest -q          # 26 tests
python eval.py               # salience 8/8 vs naive 0/8

# live: add a Qwen Cloud (DashScope) key, prove cross-session recall
cp .env.example .env         # set QWEN_API_KEY
python -m memoryagent.cli    # memory persists across runs

# service face
pip install -e ".[service]"
uvicorn memoryagent.app:app --port 8000
```

## Deliverables checklist

- [x] Working agent — CLI + FastAPI service (`src/memoryagent/`)
- [x] Built on Qwen Cloud (DashScope OpenAI-compatible; `qwen3.7-plus`, `text-embedding-v4`)
- [x] Keyless test suite — 26 tests, CI on Python 3.9–3.12 (parked as `docs/ci-workflow.yml.txt`; copy to `.github/workflows/ci.yml` to enable)
- [x] Evaluation quantifying the memory engine (`eval.py` — 8/8 vs 0/8)
- [x] Architecture diagram (`docs/architecture.svg`)
- [x] Demo script for the <3-min video (`docs/demo-script.md`)
- [x] Deploy guide for Alibaba Cloud (`DEPLOY.md` + `Dockerfile`)
- [x] Live cross-session transcript on Qwen Cloud (`docs/sample-run.md`)
- [x] Build-journey blog draft, bonus prize (`docs/blog-build-journey.md`)
- [x] License (MIT) + third-party notices

## Bonus

Build-journey writeup in [`docs/blog-build-journey.md`](docs/blog-build-journey.md) — the
salience-budget design, keyless testing approach, and the forgetting mechanism.

---

© Digital Real-Estate Frontier, LLC. Released under the MIT License.
