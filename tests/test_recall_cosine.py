"""Recall hot-path: hoisting the query-vector norm out of the per-item loop
must be *behaviour-preserving* (identical scores/ordering) while computing that
norm exactly once per recall instead of once per stored memory.

Guards the [qwen-recall-cosine] optimization: `_cosine` recomputed the query
vector's norm (`nb`) for every fact+episode on every recall — O(N) redundant
sqrt over the whole store. `recall` now hoists it via `_cosine(a, b, b_norm)`.
"""
import math

from memoryagent import memory as mem
from memoryagent.memory import _cosine, _norm


def test_precomputed_norm_is_bit_identical_to_recomputing():
    # For arbitrary vectors, passing b_norm must give the exact same float as
    # letting _cosine recompute it — the whole optimization rests on this.
    cases = [
        ([1.0, 2.0, 3.0], [3.0, 2.0, 1.0]),
        ([0.0, 0.0, 0.0], [1.0, 1.0, 1.0]),   # degenerate a-norm -> 0.0 both ways
        ([2.5, -1.0, 4.2, 0.3], [0.1, 0.9, -2.0, 1.0]),
        ([7.0], [7.0]),
    ]
    for a, b in cases:
        assert _cosine(a, b) == _cosine(a, b, _norm(b))


def test_recall_computes_query_norm_once_not_per_item(store, monkeypatch):
    # A store with several memories; recall must call _norm exactly once
    # (for the query) — proving the norm is no longer recomputed per item.
    for i in range(12):
        store.add_fact(f"durable fact {i} about hiking mountains trails rivers")

    calls = {"n": 0}
    real_norm = mem._norm

    def counting_norm(v):
        calls["n"] += 1
        return real_norm(v)

    monkeypatch.setattr(mem, "_norm", counting_norm)
    picked, _ = store.recall("hiking mountains", token_budget=100000, top_k=100)

    assert picked, "recall returned nothing"
    assert calls["n"] == 1, (
        f"query norm should be computed once per recall, was {calls['n']}x "
        "(regressed to per-item recomputation)"
    )


def test_recall_ordering_matches_bruteforce_reference(store):
    # The hoisted-norm recall must produce the SAME salience ordering as a
    # brute-force reference that scores every item with plain _cosine.
    facts = [
        "the user loves hiking in the rocky mountains",
        "the user drives a red toyota pickup truck",
        "the user studies coral reefs as a marine biologist",
        "the user enjoys mountain trails and forest rivers",
    ]
    for f in facts:
        store.add_fact(f)

    query = "tell me about mountains hiking trails"
    picked, _ = store.recall(query, token_budget=100000, top_k=100)

    # Reference: re-score every item independently with the un-hoisted path.
    from memoryagent import qwen
    q_emb = qwen.embed(query)[0]
    ref = sorted(
        store.facts + store.episodic,
        key=lambda it: store._salience(it, q_emb),  # b_norm defaults -> recompute
        reverse=True,
    )
    assert [p["text"] for p in picked] == [r["text"] for r in ref[: len(picked)]]
