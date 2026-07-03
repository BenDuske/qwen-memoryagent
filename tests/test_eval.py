# Aegis MemoryAgent — © 2026 Ben Duske. Licensed under the MIT License (see LICENSE).
"""Direct coverage for eval.py — the HEADLINE metric harness.

eval.py is the script judges run to check Track 1's hard claim ("recall the most
salient memories within a limited context window"). It reports the 8/8-salience
vs 0/8-naive verdict quoted in SUBMISSION.md. It previously had ZERO tests, so a
silent bug (e.g. a naive baseline that accidentally also keeps the planted memory,
or a budget that never binds) could produce a *wrong* headline and nobody would
know. These tests pin the invariants that make the verdict meaningful:

  * the keyless embedder is deterministic and gives a REAL (non-degenerate)
    cosine signal — shared vocabulary scores higher than disjoint vocabulary,
  * the naive baseline honestly respects the token budget and top_k (so it is a
    fair, budget-matched comparison, not a strawman that keeps everything),
  * _build_store plants the relevant memory OLD so recency genuinely works
    against it,
  * main() in keyless mode returns 0 AND salience strictly beats naive AND naive
    genuinely misses some (proving the comparison isn't a tautology).

Runs fully keyless/offline: config.QWEN_API_KEY is forced empty so no network is
touched and the deterministic embedder is used.
"""
import importlib.util
import io
import os
import re
import sys
from contextlib import redirect_stdout

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_eval():
    """Import eval.py by path as `eval_harness` (avoids shadowing builtin eval)."""
    path = os.path.join(_REPO_ROOT, "eval.py")
    spec = importlib.util.spec_from_file_location("eval_harness", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ev():
    return _load_eval()


# --- deterministic embedder -------------------------------------------------

def test_stable_hash_is_deterministic_int(ev):
    a = ev._stable_hash("penicillin")
    b = ev._stable_hash("penicillin")
    assert a == b
    assert isinstance(a, int)
    assert ev._stable_hash("penicillin") != ev._stable_hash("amoxicillin")


def test_fake_embed_str_is_coerced_to_single_row(ev):
    out = ev._fake_embed("hello world")
    assert isinstance(out, list) and len(out) == 1
    assert len(out[0]) == ev._DIM


def test_fake_embed_is_deterministic_and_counts_tokens(ev):
    once = ev._fake_embed(["alpha beta"])[0]
    twice = ev._fake_embed(["alpha beta"])[0]
    assert once == twice  # deterministic
    # a repeated token accumulates weight in its bucket
    single = ev._fake_embed("alpha")[0]
    doubled = ev._fake_embed("alpha alpha")[0]
    bucket = ev._stable_hash("alpha") % ev._DIM
    assert doubled[bucket] == pytest.approx(2 * single[bucket])
    assert single[bucket] > 0.0


def test_fake_embed_gives_a_real_cosine_signal(ev):
    """The verdict is only meaningful if similarity is real: shared vocabulary
    must score higher than disjoint vocabulary."""
    from memoryagent.memory import _cosine

    planted = ev._fake_embed("daughter Mia allergic penicillin amoxicillin")[0]
    on_topic = ev._fake_embed("what antibiotic is safe for daughter Mia")[0]
    off_topic = ev._fake_embed("the office printer jammed again today")[0]
    assert _cosine(planted, on_topic) > _cosine(planted, off_topic)


# --- naive baseline is a FAIR, budget-matched comparator --------------------

class _FakeStore:
    def __init__(self, facts, episodic):
        self.facts = facts
        self.episodic = episodic


def test_naive_recall_respects_budget_and_topk_and_recency(ev):
    from memoryagent.memory import _approx_tokens

    now = 1_000_000.0
    # 8 items, each ~5 tokens (20 chars); a budget of 20 tokens => ~4 fit.
    episodic = [
        {"text": "word word word word " * 1, "ts": now - i}
        for i in range(8)
    ]
    store = _FakeStore(facts=[], episodic=episodic)
    budget, top_k = 20, 6
    picked = ev._naive_recall(store, budget, top_k)

    used = sum(_approx_tokens(it["text"]) for it in picked)
    assert used <= budget                      # never overflows the budget
    assert len(picked) <= top_k                # respects the cap
    ts = [it["ts"] for it in picked]
    assert ts == sorted(ts, reverse=True)      # most-recent-first ordering


def test_naive_recall_topk_binds_before_budget(ev):
    now = 5.0
    # many tiny items so top_k, not budget, is the binding constraint
    episodic = [{"text": "hi", "ts": now - i} for i in range(20)]
    store = _FakeStore(facts=[], episodic=episodic)
    picked = ev._naive_recall(store, token_budget=10_000, top_k=3)
    assert len(picked) == 3


# --- store construction: relevant memory is planted OLD ---------------------

def test_build_store_plants_relevant_memory_old(ev, monkeypatch):
    monkeypatch.setattr(ev.qwen, "embed", ev._fake_embed)
    now = 2_000_000.0
    planted = "User's daughter Mia is allergic to penicillin"
    store = ev._build_store(now, planted)

    rel = [it for it in store.episodic if it["text"] == planted]
    assert len(rel) == 1
    assert rel[0]["ts"] == now - 25 * ev.DAY          # aged 25 days
    distractors = [it for it in store.episodic if it["text"] != planted]
    assert distractors, "distractors were planted"
    # every distractor is strictly more recent than the planted memory
    assert all(d["ts"] > rel[0]["ts"] for d in distractors)


# --- main(): the headline verdict -------------------------------------------

def _run_main_keyless(ev, monkeypatch):
    # Force keyless: no key => deterministic embedder, no network.
    monkeypatch.setattr(ev.config, "QWEN_API_KEY", "", raising=False)
    # main() reassigns qwen.embed; record original so monkeypatch restores it.
    monkeypatch.setattr(ev.qwen, "embed", ev.qwen.embed, raising=False)
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = ev.main()
    return rc, buf.getvalue()


def test_main_keyless_passes_and_salience_beats_naive(ev, monkeypatch):
    rc, out = _run_main_keyless(ev, monkeypatch)
    assert rc == 0
    assert "keyless deterministic embeddings" in out
    assert "PASS" in out and "VERDICT" in out


def test_main_naive_genuinely_misses_not_a_tautology(ev, monkeypatch):
    """Parse the hit-rate line and assert naive < salience AND naive drops some.
    If naive also kept everything, the comparison would be meaningless."""
    _, out = _run_main_keyless(ev, monkeypatch)
    m = re.search(r"recall hit-rate\s+(\d+)/(\d+)\s+(\d+)/(\d+)", out)
    assert m, f"hit-rate line not found in:\n{out}"
    naive_hits, n, sal_hits, n2 = (int(m.group(i)) for i in (1, 2, 3, 4))
    assert n == n2 == len(ev.SCENARIOS)
    assert sal_hits > naive_hits          # salience beats naive (the claim)
    assert naive_hits < n                 # naive genuinely drops relevant memories
    assert sal_hits >= naive_hits


def test_main_review_path_when_salience_no_better(ev, monkeypatch):
    """Cover the REVIEW branch + rc=1: if the salience engine is neutered so it
    can't outperform naive, main must report REVIEW and return non-zero."""
    monkeypatch.setattr(ev.config, "QWEN_API_KEY", "", raising=False)
    monkeypatch.setattr(ev.qwen, "embed", ev.qwen.embed, raising=False)

    # Make recall return nothing so salience can never beat naive.
    from memoryagent.memory import MemoryStore
    monkeypatch.setattr(MemoryStore, "recall",
                        lambda self, *a, **k: ([], None))
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = ev.main()
    out = buf.getvalue()
    assert rc == 1
    assert "REVIEW" in out
