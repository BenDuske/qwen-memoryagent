#!/usr/bin/env python3
"""Evaluation harness — does the salience budget actually beat naive recency?

Track 1's hard claim is "recall the most salient memories within a limited context
window." This script *measures* that claim instead of asserting it: it plants one
relevant-but-OLD memory in a sea of recent-but-irrelevant chatter, then asks the
store to recall under a tight token budget two ways:

  naive    — most-recent-first, packed into the budget (recency only)
  salience — MemoryStore.recall: similarity x recency x importance (the real engine)

A "hit" means the planted relevant memory survived into the bounded recall. We report
hit-rate over many scenarios. If the salience engine works, it should recall the
relevant old memory that naive truncation throws away.

Runs KEYLESS and deterministic by default (a stable hashing bag-of-words embedding,
so cosine similarity is real). If QWEN_API_KEY/DASHSCOPE_API_KEY is set, it uses the
*real* Qwen Cloud embedder instead — same harness, live semantics.

    python eval.py                 # keyless, reproducible
    QWEN_API_KEY=sk-... python eval.py   # real Qwen embeddings
"""
import hashlib
import os
import re
import sys
import tempfile

# Make `src/` importable so `python eval.py` works from a fresh checkout
# (mirrors demo.py). Without this, the documented keyless reproduce step fails.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from memoryagent import config, qwen
from memoryagent.memory import MemoryStore, _approx_tokens

# --- deterministic keyless embedder (mirrors tests/conftest.py) -------------
_DIM = 64
_TOKEN = re.compile(r"[a-z0-9]+")


def _stable_hash(token: str) -> int:
    return int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)


def _fake_embed(texts):
    if isinstance(texts, str):
        texts = [texts]
    out = []
    for t in texts:
        vec = [0.0] * _DIM
        for tok in _TOKEN.findall(t.lower()):
            vec[_stable_hash(tok) % _DIM] += 1.0
        out.append(vec)
    return out


# --- scenarios: (planted relevant memory, probe query sharing its topic) ----
# Distractors are generic recent chatter; the relevant memory is older, so a
# recency-only policy drops it while a salience policy should keep it.
SCENARIOS = [
    ("User's daughter Mia is allergic to penicillin and amoxicillin",
     "what antibiotic medication is safe for my daughter Mia"),
    ("User's production database runs PostgreSQL 14 on port 6543",
     "which port and PostgreSQL version is the production database on"),
    ("User prefers their coffee as a flat white with oat milk, no sugar",
     "how does the user like their coffee flat white oat milk"),
    ("User's wife Dana's birthday is on the 3rd of November",
     "when is Dana the wife birthday in November"),
    ("User drives a 2019 Subaru Outback, VIN ends 4471, blue",
     "what car does the user drive Subaru Outback blue"),
    ("User is lactose intolerant and avoids all dairy products",
     "is the user able to eat dairy lactose products"),
    ("User's AWS billing alert threshold is set to 800 dollars monthly",
     "what is the user AWS billing alert threshold in dollars"),
    ("User's son Theo plays goalkeeper for the under-12 football team",
     "what position does son Theo play football goalkeeper"),
]

DISTRACTORS = [
    "Chatted about the weather being warm today",
    "User asked for a joke and laughed",
    "Discussed weekend plans to relax",
    "User mentioned the meeting ran long",
    "Talked about a movie that was on last night",
    "User said the commute was busy this morning",
    "Mentioned the office printer was jammed again",
    "Discussed lunch options nearby",
    "User shared a funny video link",
    "Talked briefly about a podcast episode",
    "User noted the wifi was slow earlier",
    "Discussed restocking the snack drawer",
]

DAY = 86400.0


def _naive_recall(store, token_budget, top_k):
    """Baseline: most-recent-first, packed into the same budget."""
    items = sorted(store.facts + store.episodic, key=lambda it: it["ts"], reverse=True)
    picked, used = [], 0
    for it in items:
        cost = _approx_tokens(it["text"])
        if used + cost > token_budget:
            continue
        picked.append(it)
        used += cost
        if len(picked) >= top_k:
            break
    return picked


def _build_store(now, planted):
    tmp = tempfile.mkdtemp(prefix="aegis-eval-")
    store = MemoryStore(root=tmp)
    # Plant the relevant memory OLD (recency works against it).
    store.episodic.append({"text": planted, "importance": 0.4,
                           "ts": now - 25 * DAY, "emb": qwen.embed(planted)[0]})
    # Flood with RECENT distractors (recency favors them).
    for i, d in enumerate(DISTRACTORS):
        store.episodic.append({"text": d, "importance": 0.4,
                               "ts": now - (i * 0.1) * DAY, "emb": qwen.embed(d)[0]})
    return store


def main():
    keyed = bool(config.QWEN_API_KEY)
    if not keyed:
        qwen.embed = _fake_embed  # keyless deterministic mode

    import time
    now = time.time()
    budget, top_k = 80, 6  # tight: only ~6 short items fit -> the budget binds

    rows = []
    naive_hits = sal_hits = 0
    for planted, query in SCENARIOS:
        store = _build_store(now, planted)
        naive = _naive_recall(store, budget, top_k)
        sal, _ = store.recall(query, token_budget=budget, top_k=top_k)
        n_hit = any(it["text"] == planted for it in naive)
        s_hit = any(it["text"] == planted for it in sal)
        naive_hits += n_hit
        sal_hits += s_hit
        rows.append((query[:46], n_hit, s_hit))

    n = len(SCENARIOS)
    mode = "REAL Qwen embeddings" if keyed else "keyless deterministic embeddings"
    print(f"\nMemoryAgent recall evaluation  ({mode})")
    print(f"budget={budget} tokens, top_k={top_k}, {len(DISTRACTORS)} recent distractors, "
          f"1 relevant memory aged 25d\n")
    print(f"{'probe query':48} {'naive':>7} {'salience':>9}")
    print("-" * 66)
    for q, nh, sh in rows:
        print(f"{q:48} {'HIT' if nh else 'miss':>7} {'HIT' if sh else 'miss':>9}")
    print("-" * 66)
    print(f"{'recall hit-rate':48} {naive_hits}/{n:<5} {sal_hits}/{n:<7}")
    print(f"\nnaive recency:    {100*naive_hits//n:3d}%  (drops the old-but-relevant memory)")
    print(f"salience budget:  {100*sal_hits//n:3d}%  (keeps it within the same token budget)")

    ok = sal_hits > naive_hits
    print("\nVERDICT:", "PASS -- salience budget beats naive recency under budget."
          if ok else "REVIEW -- salience did not outperform naive; check tuning.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
