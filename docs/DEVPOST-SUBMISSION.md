# Devpost Submission — Aegis MemoryAgent (Track 1)

*Copy-paste-ready draft for the Devpost form. Deadline: Jul 20, 2026 @ 2:00 PM PDT.*

---

## Project title
**Aegis MemoryAgent — cross-session memory that actually forgets**

## Tagline (elevator pitch)
A Track-1 MemoryAgent on Qwen Cloud: durable cross-session recall, packed into a fixed token
budget by salience, with decay-based forgetting — and 124 keyless tests proving the memory logic
before a single token is spent.

## Track
**Track 1 — MemoryAgent**

---

## About the project (description field)

**The problem I refused to fake.** Almost every "agent with memory" demo does the same trick:
keep a running transcript and paste the whole thing back into the prompt each turn. That looks
like memory — it's a log with a context window stapled on. The day the history outgrows the
window (and it always does) the illusion breaks: the call errors, or the framework silently drops
the *oldest* turns, which are usually the most important facts about the user.

**What it does.** Aegis MemoryAgent gives an assistant three things a chat log can't:
1. **Efficient storage & retrieval** of accumulated experience.
2. **Timely forgetting** — low-value memories decay and are pruned.
3. **Recall within a limited context window** — bounded by a token budget, not a row count.

It keeps three memory layers: **episodic** (timestamped interaction summaries, decay + prune),
**facts** (durable knowledge, permanent), and **preferences** (how to serve the user,
last-write-wins so a correction *overwrites* instead of piling up). Every turn runs:
`recall(query, budget) → build bounded prompt → Qwen chat → extract new memories → forget`.

**The core idea — memory as a salience budget.** Recall candidates are scored by
`salience = similarity·0.65 + recency·0.20 + importance·0.15` and packed highest-first until a
fixed token budget is spent. No matter how many thousands of memories accumulate, the prompt that
reaches Qwen carries the same bounded, highest-value slice. I measured this against a naive
most-recent-first baseline on eight probe queries: **naive recency scored 0/8; the salience budget
scored 8/8** under the same budget. That gap is the whole project.

**Forgetting, done honestly.** Episodic memories decay on a half-life; below a salience floor they
are pruned on the next `forget()` pass. Durable facts aren't on that timer — "allergic to
penicillin" shouldn't evaporate because it's old. In the demo, five low-value episodes (small
talk) age out while all 35 facts survive.

**Running on Qwen Cloud.** 100% Qwen Cloud via DashScope's OpenAI-compatible endpoint —
`chat` on `qwen-plus`/`qwen3.7-plus`, embeddings on `text-embedding-v4`, base URL
`https://dashscope-intl.aliyuncs.com/compatible-mode/v1`. Because it speaks the OpenAI-compatible
protocol the client is tiny, and the same engine ships two faces: an interactive CLI (the cleanest
way to *prove* cross-session recall — quit, relaunch, watch it remember) and a FastAPI service.

**Proven, not vibes.** The only two functions that touch the network are `qwen.embed()` and
`qwen.chat()`. Everything else — the three-layer store, salience scoring, budget packing, decay,
pruning, last-write-wins — is pure local logic. That let me monkeypatch those two with
deterministic fakes and test the *entire* memory engine with **124 passing tests, no Qwen key
required, in ~1 second**. The build hit real bugs along the way — a `forget()` that computed decay
but never pruned, a crash that could corrupt the whole store (fixed with atomic writes), a
username that could escape its per-user memory folder, a fuzz-found UTF-8 crash — all caught and
pinned by tests. Full write-up in `docs/build-journey.md`.

**What's next.** Compaction over pure pruning (distill an episode into a durable fact before
forgetting it), an ANN vector index past tens of thousands of memories, and per-deployment
multi-tenancy hardening.

## Built with
Python · Qwen Cloud (Alibaba Cloud Model Studio / DashScope, OpenAI-compatible API) ·
`qwen-plus` / `qwen3.7-plus` · `text-embedding-v4` · FastAPI · pytest

---

## Submission links & rules checklist

| Requirement | Link / status |
|---|---|
| **Public repo + OSS license** | https://github.com/BenDuske/qwen-memoryagent — **MIT** ✅ |
| **Proof of deployment** (link to a code file using Alibaba Cloud services/APIs) | `src/memoryagent/qwen.py` → https://github.com/BenDuske/qwen-memoryagent/blob/master/src/memoryagent/qwen.py — DashScope (Alibaba Cloud Model Studio) chat + embeddings client. Supporting: `src/memoryagent/config.py` (base URL `dashscope-intl.aliyuncs.com/compatible-mode/v1`). ✅ |
| **Demo video (< 3 min)** | `qwen-memoryagent-demo-CUTA.mp4` (1:53) — upload to YouTube/Vimeo (unlisted OK) and paste the link. ✅ ready |
| **Architecture diagram** | https://github.com/BenDuske/qwen-memoryagent/blob/master/docs/architecture.png ✅ |
| **Text description** | the "About the project" section above ✅ |
| **Track ID** | Track 1 — MemoryAgent ✅ |

### Proof-of-deployment link to paste
```
https://github.com/BenDuske/qwen-memoryagent/blob/master/src/memoryagent/qwen.py
```

### Notes
- The video is hosted locally at `qwen-demo-assets/qwen-memoryagent-demo-CUTA.mp4` — Devpost wants a
  URL, so upload to YouTube (unlisted) or Vimeo first, then paste the link into the video field.
- Confirm the repo's **default branch** in the blob URLs (`master` vs `main`) before pasting.
- DashScope key rotates ~Jul 9 — not needed for submission (proof is a code-file link), but rotate
  before any live re-demo.
