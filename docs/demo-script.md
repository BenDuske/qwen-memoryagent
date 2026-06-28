# Demo Script — Aegis MemoryAgent (Qwen Cloud, Track 1)

**Target length: < 3 minutes.** Three beats, in order:
1. **Cross-session recall** — quit the process, restart, it still knows you.
2. **Bounded recall** — memory grows, but the prompt never overflows the context window.
3. **Forgetting** — low-salience episodic memory decays and is pruned.

The whole point of Track 1: an agent that remembers *across sessions* and recalls
*within a limited context window*. This script makes both observable on camera.

---

## 0 · Setup (off-camera, ~10s of prep)

```bash
cd qwen-memoryagent
pip install -e ".[service]"
# Qwen Cloud / DashScope key (DashScope OpenAI-compatible endpoint):
export QWEN_API_KEY=sk-...            # or DASHSCOPE_API_KEY
export MEMORY_DIR=./.demo-mem          # fresh, throwaway store for the recording
rm -rf ./.demo-mem
```

Have two terminals ready (or one terminal + a browser for the HTTP beat). Keep the
`MEMORY_DIR` visible somewhere — pointing at the on-disk JSONL is what proves the
memory is real and not in-context replay.

---

## Beat 1 · Cross-session recall  (0:00 – 1:10)

> **Say:** "A normal chatbot forgets you the moment the process exits. This one
> writes durable memory to disk and recalls it in a brand-new session."

**Session A** — start the CLI, teach it something, then *quit the process entirely.*

```bash
python -m memoryagent.cli
```
```
you> Hi, I'm Ben. I'm allergic to peanuts and I prefer short, blunt answers.
aegis> Got it, Ben — noted the peanut allergy, and I'll keep it short.
you> I'm planning a trip to Lisbon in October.
aegis> Nice. Want blunt tips for Lisbon in October?
you> ^C
Memory saved. Bye.
```

**Show the proof it's on disk, not in context:**
```bash
ls ./.demo-mem
cat ./.demo-mem/facts.jsonl     # peanut allergy + Lisbon trip, with embeddings
cat ./.demo-mem/prefs.json      # name=Ben, tone=short/blunt  (last-write-wins)
```

**Session B** — *new process, no chat history replayed.* It greets you with the
loaded counts and recalls without being re-told.

```bash
python -m memoryagent.cli
```
```
Aegis MemoryAgent — Qwen Cloud (Track 1). Memory persists across sessions.
  loaded: 2 facts · 2 episodes · 1 prefs  (./.demo-mem)
you> What should I avoid eating, and remind me where I'm headed next month?
aegis> Peanuts — you're allergic. And you're headed to Lisbon in October.
```

> **Say:** "Different process. Nothing was replayed. The recall came from the
> on-disk store, ranked and injected just-in-time."

---

## Beat 2 · Bounded recall  (1:10 – 2:05)

> **Say:** "Memory grows forever, but the prompt can't. Recall is packed into a
> fixed token budget by salience = similarity × recency × importance."

Easiest to *show* this via the HTTP service, which exposes recall directly.

```bash
uvicorn memoryagent.app:app --port 8000   # second terminal
```

Pile on a lot of memory for one user, then inspect what recall actually selects:

```bash
# add many facts
for i in $(seq 1 40); do
  curl -s localhost:8000/chat -H 'content-type: application/json' \
    -d "{\"user\":\"ben\",\"text\":\"For the record, fact number $i is XYZ-$i.\"}" >/dev/null
done

# 40+ facts on disk...
curl -s localhost:8000/memory/ben/stats

# ...but recall for a query returns only the highest-salience few, under budget:
curl -s "localhost:8000/memory/ben/recall?q=what+am+I+allergic+to&budget=400&top_k=5"
```

> **Say:** "Forty-plus memories stored, but only the handful that matter for *this*
> query get injected, and only until the token budget is hit. That's the
> 'recall within a limited context window' guarantee — made observable."

Default budget is `RECALL_TOKEN_BUDGET=1200`, `RECALL_TOP_K=8` (env-tunable). Drop
`budget` low on camera to make the cap obvious — fewer items come back.

---

## Beat 3 · Forgetting  (2:05 – 2:45)

> **Say:** "And it forgets. Episodic memory decays on a half-life; once salience
> falls below the floor, it's pruned — so the store doesn't grow without bound."

```bash
# episodic count before
curl -s localhost:8000/memory/ben/stats

# force a forgetting pass (also runs automatically after every turn)
curl -s -X POST localhost:8000/memory/ben/forget
```
```json
{"dropped": 7, "stats": {"facts": 42, "episodes": 5, "prefs": 1, "dir": "..."}}
```

> **Say:** "Durable *facts* and *preferences* stay. Low-value *episodes* age out.
> Half-life and floor are both tunable — `DECAY_HALFLIFE_DAYS`, `SALIENCE_FLOOR`."

To show real pruning on camera without waiting 14 days, set an aggressive decay for
the recording: `export DECAY_HALFLIFE_DAYS=0.0001 SALIENCE_FLOOR=0.5` before the run,
so freshly-added episodes drop on the next `forget`.

---

## Close  (2:45 – 3:00)

> **Say:** "Cross-session recall, bounded by a token budget, with decay-based
> forgetting — same engine behind a CLI and a FastAPI service, deployable on
> Alibaba Cloud. All original code, MIT, running on Qwen Cloud."

Show one frame each: `docs/architecture.svg`, `DEPLOY.md` (Function Compute / ECS),
the green `pytest` run. Done.

---

### Shot list / cheat sheet
| Time | Beat | Command | What to point at |
|------|------|---------|------------------|
| 0:00 | Teach | `python -m memoryagent.cli` (Session A) | typing facts + prefs |
| 0:35 | Proof | `cat ./.demo-mem/facts.jsonl` | memory is on disk |
| 0:50 | Recall | `python -m memoryagent.cli` (Session B) | "loaded: N facts" + answer |
| 1:10 | Bound | `curl .../recall?budget=400` | few items, under budget |
| 2:05 | Forget | `curl -X POST .../forget` | `"dropped": N` |
| 2:45 | Close | architecture.svg + pytest | the whole picture |

> Recording without a key? The `pytest` suite monkeypatches `qwen.embed/chat`, so you
> can still film the bounded-recall and forgetting *logic* deterministically — but the
> cross-session conversation beat needs a real Qwen Cloud key to be convincing.
