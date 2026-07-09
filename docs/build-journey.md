# The MemoryAgent that had to earn its forgetting — a build journey on Qwen Cloud

*Track 1 (MemoryAgent), Global AI Hackathon Series with Qwen Cloud. This is the honest version —
what broke, what I changed, and why the bugs are the reason I trust it.*

## The thing I refused to fake

Most "agent with memory" demos are a magic trick: keep a running transcript, paste the whole
thing back into the prompt every turn. It *looks* like memory. It's a log with a context window
stapled on. The day the history outgrows the window — and it always does — the illusion breaks:
the call errors, or the framework silently truncates the *oldest* turns, which are usually the
most important facts about the user.

Track 1 asks for the three things that separate a real MemoryAgent from a chat log:

1. **Efficient storage & retrieval** of accumulated experience.
2. **Timely forgetting** — letting stale things go.
3. **Recall within a limited context window.**

I decided the project would live or die on those three, and that I'd build it so the memory
logic was *provable without spending a single token*.

## The core idea: memory as a salience budget

Three layers, because not all memory is the same shape or cost:

| Layer | Holds | Recalled by |
|------|-------|-------------|
| **Episodic** | timestamped interaction summaries | semantic + recency-decayed, prunable |
| **Facts** | durable knowledge about the user/world | semantic top-k, permanent |
| **Preferences** | how the user wants to be served | always injected, last-write-wins |

Every turn runs the same five steps:

```
recall(query, budget) → build bounded prompt → Qwen chat → extract new memories → forget
```

The part I'm proudest of: **recall is bounded by a token budget, not a row count.** Candidates
are scored by salience and packed highest-first until the budget is spent:

```python
salience = similarity * 0.65 + recency * 0.20 + importance * 0.15
```

No matter how many thousands of memories accumulate, the prompt that reaches Qwen carries the
same bounded, highest-value slice. That's the "limited context window" requirement solved
structurally, not hoped-for. I proved it with `eval.py`: plant one relevant memory aged 25 days
in a flood of 12 recent-but-irrelevant distractors, recall under a tight budget. Naive
most-recent-first: **0 of 8** probe queries hit. The salience budget: **8 of 8.** That gap is
the whole project.

## Now the honest part — the bugs that made it real

A design that only ever ran on the happy path isn't a system; it's a slide. Here's what actually
broke, in the order the pain arrived. Twenty-four fixes shipped; these are the ones that changed
how I think about the thing.

### 1. The forgetting didn't forget

The first `forget()` pass computed decay scores, logged them, and... never deleted anything. The
store grew forever behind a function *named* forget. It's the most embarrassing kind of bug — the
one where the feature is a print statement. Fix: actually drop episodes whose decayed salience
falls below the floor, and pin the invariant with a test that fails if a below-floor episode
survives a pass. **Lesson: name a thing "forget" and it had better prune, or you've shipped a leak
with good branding.**

### 2. A crash could eat your entire memory

The store wrote in place. A crash — or a full disk — *mid-write* left a half-written JSONL that
wouldn't parse on next load, and the tolerant loader would drop the corrupt file: every memory,
gone. For a *memory* agent, that's the cardinal sin. Fix: atomic writes — serialize to a temp
file, `fsync`, then `os.replace` (atomic on POSIX and Windows). A crash now costs you at most the
last turn, never the whole history. Paired with a tolerant loader that skips a single bad *line*
instead of failing the whole file.

### 3. A username could walk out of its own memory

The multi-user HTTP service keyed each user's store by username as a path segment. A crafted
all-dots username (`...`) walked the path *up and out* of its per-user folder — a classic
traversal, in the one place where crossing users' memories is the worst possible outcome. Fix:
reject path-escaping usernames outright and pin every store under a single root directory, with a
test that asserts the escape is blocked.

### 4. Untrusted model output was poisoning every future prompt

Memories are *extracted by the model* from the conversation — which means the extractor's output
is untrusted. A malformed preference *value* (a dict where a string belonged) got `repr()`'d and
baked into the system prompt on **every subsequent turn** — a self-inflicted prompt-injection that
would ride along forever. Fix: guard the preference value's type at learn time so a bad-typed blob
can't become permanent instruction text.

### 5. The demo-day failures — silence and tracebacks

Two that only bite you live, on camera, at the worst moment:
- A **missing API key** made the client hang for ~120 seconds before failing — looks like a freeze.
  Fixed to fail fast with a clear message.
- An **expired or rejected Qwen key** (mine expires ~Jul 9) dumped a raw traceback instead of a
  human "your key was rejected." Fixed to degrade cleanly.
- Bad numeric env vars (`RECALL_TOP_K=` empty, or garbage) **crashed the import** instead of falling
  back to the default. Fixed to degrade to the documented default.

### 6. The quiet correctness ones

The bugs nobody sees but that decide whether recall is *right*:
- **Duplicate text wasted a budget slot** — the same memory packed twice ate room the budget should
  have spent on something new. Now deduped at pack time.
- **`budget=0` / `top_k=0` weren't observable** — the boundary silently returned defaults, so you
  couldn't prove the cap worked. Now honored exactly.
- **Importance wasn't clamped** to `[0,1]`, so an out-of-range extraction could dominate salience.
  Clamped at the recall/forget boundaries.
- **A fuzz-found availability bug:** invalid UTF-8 in the store file crashed recall. Now the bad
  line is skipped, not fatal.
- **A threadpool race** in the service could build two agents for one user at once and lose a write.
  Serialized get-or-create per user.
- **The Docker image could bake the live key** — no `.dockerignore`, so `.env` (with a real
  `QWEN_API_KEY`) would ship inside the image. Added `.dockerignore`; the key never enters a layer.

Every one of those has a test pinning it. That's the point of the next section.

## Why I could catch all of this without a key

The biggest engineering decision wasn't about memory — it was the **seam**. The only two functions
that touch the network are `qwen.embed()` and `qwen.chat()`. Everything else — the three-layer
store, salience scoring, budget packing, decay, pruning, last-write-wins — is pure local logic.

So I monkeypatch those two with deterministic fakes and test the *entire* engine without a token.
The fake embedder is a stable hashing bag-of-words vector, so cosine similarity is **real math** —
recall ranking is genuinely verifiable, not stubbed to a constant:

```
pytest    # 102 tests, ~1s, no Qwen key required
```

Almost every bug above was found and fixed *keyless*, in that fast loop — the forgetting leak, the
corruption case, the path escape, the fuzz crash, the budget-boundary cases. When I wire in real
Qwen Cloud credentials, nothing about the memory logic changes; only the two leaf functions start
hitting the network.

## Running on Qwen Cloud

100% Qwen Cloud via DashScope's OpenAI-compatible endpoint:

- **Chat:** `qwen3.7-plus` (swappable to `qwen-max`)
- **Embeddings:** `text-embedding-v4`
- **Base URL:** `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`

Because it speaks the OpenAI-compatible protocol, the client is tiny — and the same engine ships
two faces: an interactive CLI (the cleanest way to *prove* cross-session recall — quit, relaunch,
watch it remember) and a FastAPI service (`POST /chat`, `GET /memory/{user}/recall`,
`POST /memory/{user}/forget`) that drops onto Alibaba Cloud ECS / Simple App Server. The
`Dockerfile`, `.dockerignore`, and `DEPLOY.md` cover the deployment; `/healthz` returns
`{"ok": true}` on the live instance.

## What I'd do next

- **Compaction over pure pruning** — when an episode is about to be forgotten, optionally distill it
  into a durable fact first, so the *lesson* survives even when the *event* doesn't.
- **A real vector index** — the current cosine scan is O(n) per recall; fine at hackathon scale, but
  past tens of thousands of memories it wants an ANN index (or DashScope's vector store).
- **Per-deployment multi-tenancy** hardening beyond the path-escape fix — quotas and per-user rate limits.

## Takeaways

Two lessons kept paying off. **Put the network behind the smallest possible seam** — two functions —
so the hard part (forgetting correctly) is provably correct before a token is spent. And **treat your
own model's output as untrusted input**: the prompt-poisoning bug and the extractor type guards came
from taking that seriously.

A MemoryAgent isn't a chatbot with a long memory. It's a system that decides, every turn, what's
worth remembering and what's earned the right to be forgotten — and, as the bug list shows, one that
has to survive crashes, hostile usernames, bad bytes, and its own expired keys while doing it. Built
on Qwen Cloud, that turned out to be the fun part.

---

*Repo: MIT-licensed, runs keyless for tests. © 2026 Digital Real-Estate Frontier, LLC.*
