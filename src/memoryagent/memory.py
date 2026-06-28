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


def _cosine(a, b) -> float:
    s = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
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

    def _load_jsonl(self, name):
        out = []
        p = self._p(name)
        if os.path.exists(p):
            for line in open(p, encoding="utf-8"):
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out

    def _save_jsonl(self, name, items):
        with open(self._p(name), "w", encoding="utf-8") as f:
            for it in items:
                f.write(json.dumps(it, ensure_ascii=False) + "\n")

    def _load_prefs(self):
        p = self._p("prefs.json")
        return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}

    def _save_prefs(self):
        json.dump(self.prefs, open(self._p("prefs.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)

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
    def _salience(self, item, q_emb):
        sim = _cosine(item["emb"], q_emb)
        age_days = (_now() - item["ts"]) / 86400.0
        recency = 0.5 ** (age_days / config.DECAY_HALFLIFE_DAYS)
        return sim * 0.65 + recency * 0.20 + item.get("importance", 0.4) * 0.15

    def recall(self, query: str, token_budget: int = None, top_k: int = None):
        token_budget = token_budget or config.RECALL_TOKEN_BUDGET
        top_k = top_k or config.RECALL_TOP_K
        q_emb = qwen.embed(query)[0]
        scored = [(self._salience(it, q_emb), it) for it in (self.facts + self.episodic)]
        scored.sort(key=lambda x: x[0], reverse=True)
        picked, used = [], 0
        for _, it in scored:
            cost = _approx_tokens(it["text"])
            if used + cost > token_budget:
                continue
            picked.append(it)
            used += cost
            if len(picked) >= top_k:
                break
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
