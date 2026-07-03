# Aegis MemoryAgent — © 2026 Ben Duske. Licensed under the MIT License (see LICENSE).
"""The 3-layer memory store — the heart of the MemoryAgent.

  Episodic   timestamped interaction summaries     (decays, can be pruned/compacted)
  Facts      durable knowledge about user/world     (semantic recall)
  Preferences how the user wants to be served        (last-write-wins, always injected)

Recall is BOUNDED: candidates are ranked by salience = similarity x recency x importance,
then packed into a token budget so the prompt never overflows the context window no matter
how large memory grows. Forgetting prunes episodic memories whose salience has decayed
below a floor. All persisted as plain JSONL/JSON under MEMORY_DIR.
"""
import json
import math
import os
import time
from . import config, qwen


def _now() -> float:
    return time.time()


def _norm(v) -> float:
    return math.sqrt(sum(x * x for x in v))


def _cosine(a, b, b_norm: float = None) -> float:
    # b_norm lets a caller hoist the query-vector norm out of a recall loop:
    # it is recomputed here only when not supplied, so results are identical.
    s = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = b_norm if b_norm is not None else _norm(b)
    return s / (na * nb) if na and nb else 0.0


def _approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)  # ~4 chars/token


class MemoryStore:
    def __init__(self, root: str = None):
        self.root = root or config.MEMORY_DIR
        os.makedirs(self.root, exist_ok=True)
        self.episodic = self._load_jsonl("episodic.jsonl")
        self.facts = self._load_jsonl("facts.jsonl")
        self.prefs = self._load_prefs()

    # ---- persistence ----
    def _p(self, name):
        return os.path.join(self.root, name)

    def _atomic_write(self, name, render):
        # Crash-safe write: render fully to a temp file, fsync, then os.replace()
        # (atomic on POSIX and Windows for same-dir paths). A crash/power-loss
        # mid-write leaves the old file intact instead of a torn one, so a single
        # interrupted save can never corrupt the store and take down startup.
        p = self._p(name)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            render(f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)

    def _load_jsonl(self, name):
        out = []
        p = self._p(name)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        # Defense-in-depth: a single torn/corrupt record (e.g. from a
                        # pre-atomic-write crash or external tampering) must not nuke
                        # the whole store — skip it, keep every valid memory.
                        continue
        return out

    def _save_jsonl(self, name, items):
        def render(f):
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")
        self._atomic_write(name, render)

    def _load_prefs(self):
        p = self._p("prefs.json")
        if not os.path.exists(p):
            return {}
        try:
            with open(p, encoding="utf-8") as f:
                raw = json.load(f)
        except (json.JSONDecodeError, ValueError):
            # A corrupt prefs.json degrades to empty prefs rather than crashing
            # __init__ (which would make the whole agent unstartable).
            return {}
        return self._normalize_prefs(raw)

    @staticmethod
    def _normalize_prefs(raw):
        # set_pref always writes {"value": ..., "ts": ...}, but a legacy, migrated,
        # or hand-edited prefs.json can be valid JSON yet carry a different shape
        # (e.g. a bare {"name": "Ben"}). Consumers like agent._build_system read
        # v["value"] for every pref, so a bare value there raises TypeError and
        # crashes EVERY chat turn on the recall path — before the user gets a reply.
        # Normalise at the boundary so the in-memory prefs always have the expected
        # shape: keep a well-formed {"value": ...} entry as-is, wrap anything else.
        if not isinstance(raw, dict):
            return {}
        out = {}
        for k, v in raw.items():
            if isinstance(v, dict) and "value" in v:
                out[str(k)] = v
            else:
                out[str(k)] = {"value": v, "ts": 0.0}
        return out

    def _save_prefs(self):
        self._atomic_write(
            "prefs.json",
            lambda f: json.dump(self.prefs, f, ensure_ascii=False, indent=2),
        )

    # ---- writes ----
    def add_fact(self, text: str, importance: float = 0.6):
        text = text.strip()
        if not text or any(f["text"] == text for f in self.facts):
            return
        self.facts.append({"text": text, "importance": importance,
                           "ts": _now(), "emb": qwen.embed(text)[0]})
        self._save_jsonl("facts.jsonl", self.facts)

    def add_episode(self, summary: str, importance: float = 0.4):
        summary = summary.strip()
        if not summary:
            return
        self.episodic.append({"text": summary, "importance": importance,
                              "ts": _now(), "emb": qwen.embed(summary)[0]})
        self._save_jsonl("episodic.jsonl", self.episodic)

    def set_pref(self, key: str, value):
        # last-write-wins: a correction overwrites, it never piles up
        self.prefs[str(key)] = {"value": value, "ts": _now()}
        self._save_prefs()

    # ---- recall (bounded by token budget) ----
    def _salience(self, item, q_emb, q_norm: float = None):
        sim = _cosine(item["emb"], q_emb, q_norm)
        age_days = (_now() - item["ts"]) / 86400.0
        recency = 0.5 ** (age_days / config.DECAY_HALFLIFE_DAYS)
        return sim * 0.65 + recency * 0.20 + item.get("importance", 0.4) * 0.15

    def recall(self, query: str, token_budget: int = None, top_k: int = None):
        # `is None`, not `or`: an explicit budget/top_k of 0 is a legitimate probe of
        # the recall boundary (the /recall endpoint exists to make the bound
        # observable), so it must be honored — `x or default` would silently coerce
        # 0 back to the full default and return a misleading non-empty result.
        token_budget = config.RECALL_TOKEN_BUDGET if token_budget is None else token_budget
        top_k = config.RECALL_TOP_K if top_k is None else top_k
        q_emb = qwen.embed(query)[0]
        q_norm = _norm(q_emb)  # hoisted out of the per-item loop (was recomputed N times)
        scored = [(self._salience(it, q_emb, q_norm), it) for it in (self.facts + self.episodic)]
        scored.sort(key=lambda x: x[0], reverse=True)
        picked, used, seen = [], 0, set()
        for _, it in scored:
            # top_k check FIRST so top_k=0 honestly returns nothing (a post-append
            # check would still emit one item before breaking). For any positive
            # top_k this is behaviour-identical — the cap binds at the same count.
            if len(picked) >= top_k:
                break
            # Skip a memory whose text was already packed: facts+episodic are merged
            # and add_episode does not dedup, so identical text can appear twice.
            # Spending the bounded budget on a duplicate would starve a distinct
            # memory of its slot; the highest-salience copy is kept, later ones dropped.
            key = it["text"].strip()
            if key in seen:
                continue
            cost = _approx_tokens(it["text"])
            if used + cost > token_budget:
                continue
            picked.append(it)
            used += cost
            seen.add(key)
        return picked, self.prefs

    # ---- forgetting ----
    def forget(self) -> int:
        """Prune episodic memories whose decayed salience fell below the floor."""
        kept = []
        for it in self.episodic:
            age_days = (_now() - it["ts"]) / 86400.0
            recency = 0.5 ** (age_days / config.DECAY_HALFLIFE_DAYS)
            sal = recency * 0.6 + it.get("importance", 0.4) * 0.4
            if sal >= config.SALIENCE_FLOOR:
                kept.append(it)
        dropped = len(self.episodic) - len(kept)
        if dropped:
            self.episodic = kept
            self._save_jsonl("episodic.jsonl", self.episodic)
        return dropped

    def stats(self):
        return {"facts": len(self.facts), "episodes": len(self.episodic),
                "prefs": len(self.prefs), "dir": self.root}
