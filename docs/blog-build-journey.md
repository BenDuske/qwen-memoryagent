# Building a MemoryAgent that actually forgets — on Qwen Cloud

*A build-journey writeup for the Global AI Hackathon Series with Qwen Cloud (Track 1: MemoryAgent).*

## The problem I refused to fake

Almost every "agent with memory" demo I've seen does the same trick: it keeps a running
transcript and pastes the whole thing back into the prompt each turn. It looks like memory.
It is actually a log with a context window stapled to it. The day the history outgrows the
window — and it always does — the illusion breaks: either the call errors, or the framework
silently truncates the *oldest* turns, which are often the most important facts about the user.

Track 1 of the Qwen Cloud hackathon asks for the three things that distinguish a real
MemoryAgent from a chat log:

1. **Efficient storage & retrieval** of accumulated experience.
2. **Timely forgetting** — letting stale things go.
3. **Recall within a limited context window.**

I decided the whole project would live or die on those three, and that I'd build something I
could *test without spending a single token* so the memory logic was provable, not vibes.

## The core idea: memory as a salience budget

The agent keeps three layers, because not all memory is the same shape or the same cost:

| Layer | Holds | Update cost | How it's recalled |
|------|-------|-------------|-------------------|
| **Episodic** | timestamped interaction summaries | cheap | semantic + recency-decayed |
| **Facts** | durable knowledge about the user/world | cheap | semantic top-k |
| **Preferences** | how the user wants to be served | trivial | always injected (small) |

Every turn runs the same five steps:

```
recall(query, budget) → build bounded prompt → Qwen chat → extract new memories → forget
```

The part I'm proudest of is that **recall is bounded by a token budget, not a row count.**
Candidates are scored by salience and packed highest-first until the budget is spent:

```python
salience = similarity * 0.65 + recency * 0.20 + importance * 0.15
```

```python
for _, item in scored:                 # sorted by salience, descending
    cost = approx_tokens(item["text"])
    if used + cost > token_budget:     # default 1200 tokens
        continue
    picked.append(item); used += cost
    if len(picked) >= top_k: break     # default 8
```

No matter how many thousands of memories accumulate, the prompt that reaches Qwen carries
the same bounded, highest-value slice. That's the "limited context window" requirement, solved
structurally instead of hoped-for.

`recency` is a real exponential decay — `0.5 ** (age_days / 14)` — so a memory loses half its
recency weight every two weeks. Similarity dominates (0.65) so an old-but-relevant fact still
beats a fresh-but-irrelevant one; recency is a tie-breaker, not the ranking.

## Forgetting was the hard part — and the interesting one

It's easy to *add* memory. Deciding what to drop is where most systems cheat (they never drop,
and call unbounded growth a feature). Two mechanisms keep this store honest:

- **Episodic decay + prune.** Each episode's standalone salience decays with age. Below a floor
  (`SALIENCE_FLOOR = 0.12`) it's pruned on the next `forget()` pass. Importantly, facts aren't
  on this timer — a durable fact ("user is allergic to penicillin") shouldn't evaporate just
  because it's old. Only the low-importance, time-bound episodic chatter does.
- **Last-write-wins preferences.** When a user corrects a preference ("actually, metric units"),
  the new value *overwrites* the old one keyed by name. Corrections don't pile up as contradictory
  memories the way they do in append-only transcript systems — the agent simply stops being wrong.

That second point is subtle and it's the thing append-a-transcript designs get wrong every time:
they remember both the mistake and the correction, and then have to reason their way out of the
contradiction on every turn.

## Why I could build the whole engine keyless

The biggest engineering decision wasn't about memory at all — it was the seam. The only two
functions that touch the network are `qwen.embed()` and `qwen.chat()`. Everything else — the
three-layer store, salience scoring, budget packing, decay, pruning, last-write-wins — is pure
local logic with no API dependency.

That meant I could monkeypatch those two functions with deterministic fakes and test the *entire*
memory engine without a key. The fake embedder is a stable hashing bag-of-words vector, so cosine
similarity is **real math** — recall ranking is genuinely verifiable, not stubbed to a constant:

```python
pytest    # 18 tests, ~1s, no Qwen key required
```

The suite proves the things the rubric actually cares about: cross-session persistence (write in
one process, recall in a fresh one), bounded recall (a 50-memory store still respects the token
budget), decay-based forgetting (stale episodes get pruned, durable facts survive), and
last-write-wins preferences. When I later wire in real Qwen Cloud credentials, *nothing about the
memory logic changes* — only the two leaf functions start hitting the network.

## Running on Qwen Cloud

The backend is 100% Qwen Cloud via DashScope's OpenAI-compatible endpoint:

- **Chat:** `qwen-plus` (swappable to `qwen-max`)
- **Embeddings:** `text-embedding-v3`
- **Base URL:** `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`

Because it speaks the OpenAI-compatible protocol, the client is tiny — and the same engine ships
two faces: an interactive CLI (the cleanest way to *prove* cross-session recall — quit, relaunch,
watch it remember) and a FastAPI service (`POST /chat`, `GET /memory/{user}/recall`,
`POST /memory/{user}/forget`) that drops into Alibaba Cloud Function Compute or an ECS container.
The `Dockerfile` and `DEPLOY.md` cover the deployment proof.

## What I'd do next

- **Compaction over pure pruning** — when an episode is about to be forgotten, optionally distill
  it into a durable fact first, so the *lesson* survives even when the *event* doesn't.
- **A real vector index** — the current cosine scan is O(n) per recall, which is fine at hackathon
  scale but would want an ANN index (or DashScope's vector store) past tens of thousands of memories.
- **Per-user namespacing in the service** so one deployment serves many users with isolated stores.

## Takeaways

The lesson that kept paying off: **put the network behind the smallest possible seam.** Two
functions. That single decision made the memory engine testable without a key, made the logic
the star instead of the API, and means the hard part — forgetting correctly — is provably correct
before a single token is ever spent.

A MemoryAgent isn't a chatbot with a long memory. It's a system that decides, every turn, what's
worth remembering and what's earned the right to be forgotten. Built on Qwen Cloud, that turned
out to be the fun part.

---

*Repo: MIT-licensed, runs keyless for tests. © 2026 Digital Real-Estate Frontier, LLC.*
