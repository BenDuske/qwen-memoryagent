"""MemoryStore: recall ranking, bounded token budget, forgetting, prefs, dedup."""
import time

import pytest

from memoryagent import config
from memoryagent.memory import MemoryStore, _approx_tokens, _clamp01


def test_recall_ranks_relevant_fact_first(store):
    store.add_fact("The user loves hiking in the Rocky Mountains")
    store.add_fact("The user drives a red Toyota pickup truck")
    store.add_fact("The user works as a marine biologist studying coral")

    picked, _ = store.recall("Tell me about the mountains and hiking trip")

    assert picked, "recall returned nothing"
    assert "hiking" in picked[0]["text"].lower()


def test_recall_is_bounded_by_token_budget(store):
    # Each fact ~ 25 words; pack many so the budget must bite.
    for i in range(30):
        store.add_fact(f"Durable fact number {i} about hiking mountains trails "
                       f"rivers forests valleys peaks summits ridges canyons {i}")

    budget = 60  # tokens
    picked, _ = store.recall("hiking mountains", token_budget=budget, top_k=100)

    used = sum(_approx_tokens(p["text"]) for p in picked)
    assert used <= budget, f"recall overflowed budget: {used} > {budget}"
    assert picked, "budget should still admit at least one memory"


def test_recall_greedy_pack_skips_oversized_for_smaller(store):
    # The pack loop must SKIP a too-big memory and keep scanning, not HALT on it:
    # a highest-salience item that overflows the budget should not block a smaller,
    # lower-salience item behind it from filling the remaining room.
    #
    # Under the bag-of-words fake embedder, "hiking mountains" repeated has a
    # perfect cosine (1.0) with the query but is long; bare "hiking" scores lower
    # (~0.707) but is tiny. So the big item ranks FIRST yet overflows the budget.
    # Existing budget tests use uniformly-sized facts and pass identically whether
    # the loop uses `continue` or `break`; this pins the greedy-pack behavior so a
    # `continue`->`break` regression (which silently under-fills recall) is caught.
    big = "hiking mountains " * 24            # perfect cosine, but oversized
    store.add_fact(big, importance=0.6)
    store.add_fact("hiking", importance=0.6)  # lower cosine, fits in the leftover

    budget = 40
    assert _approx_tokens(big) > budget, "big item must overflow the whole budget"
    picked, _ = store.recall("hiking mountains", token_budget=budget, top_k=100)

    texts = [p["text"] for p in picked]
    assert "hiking" in texts, "smaller lower-salience memory should still be packed"
    assert big not in texts, "oversized top-ranked memory should be skipped"


def test_recall_dedups_identical_text(store):
    # facts+episodic are merged at recall and add_episode does NOT dedup, so the
    # same summary can appear twice. A duplicate must not consume an output slot a
    # DISTINCT memory should hold — the highest-salience copy is kept, later exact
    # copies are dropped. Two identical high-salience episodes plus one distinct,
    # lower-salience fact; with top_k=2 the two dups would fill both slots and
    # starve the distinct memory unless recall dedups by text.
    store.add_episode("hiking mountains trip report", importance=0.6)
    store.add_episode("hiking mountains trip report", importance=0.6)  # exact dup
    store.add_fact("kayaking rivers", importance=0.6)                   # distinct, lower cosine

    picked, _ = store.recall("hiking mountains", token_budget=100000, top_k=2)

    texts = [p["text"] for p in picked]
    assert texts.count("hiking mountains trip report") == 1, "duplicate text packed twice"
    assert "kayaking rivers" in texts, "distinct memory should get the slot the dup wasted"


def test_recall_top_k_caps_count(store):
    for i in range(20):
        store.add_fact(f"hiking fact {i} mountains trails forests")
    picked, _ = store.recall("hiking mountains", token_budget=100000, top_k=5)
    assert len(picked) <= 5


def test_recall_honors_explicit_zero_budget(store):
    # The /recall endpoint exists to make the bounded-recall guarantee OBSERVABLE,
    # and 0 is the natural way to probe the boundary. `token_budget or default`
    # would coerce an explicit 0 back to the full default and return a misleading
    # non-empty result; `is None` guarding must let 0 through -> nothing fits.
    for i in range(5):
        store.add_fact(f"hiking fact {i} mountains trails forests")
    # Sanity: the same store recalls normally when no budget is given.
    assert store.recall("hiking mountains")[0], "default recall should return memories"

    picked, _ = store.recall("hiking mountains", token_budget=0)
    assert picked == [], "explicit token_budget=0 must admit nothing, not the default"


def test_recall_honors_explicit_zero_top_k(store):
    # top_k=0 means "return no items". A post-append cap would still emit one item
    # before breaking; the loop-top cap makes 0 honest. `top_k or default` would
    # also have coerced 0 back to the default.
    for i in range(5):
        store.add_fact(f"hiking fact {i} mountains trails forests")
    picked, _ = store.recall("hiking mountains", token_budget=100000, top_k=0)
    assert picked == [], "explicit top_k=0 must return nothing"


def test_forget_prunes_decayed_low_importance_episode(store):
    # Fresh, salient episode survives.
    store.add_episode("Important recent event", importance=0.9)
    # Old, low-importance episode should fall below the salience floor.
    store.add_episode("Trivial chatter from long ago", importance=0.1)
    store.episodic[-1]["ts"] = time.time() - 90 * 86400  # 90 days old

    before = len(store.episodic)
    dropped = store.forget()

    assert dropped == 1, f"expected exactly one prune, got {dropped}"
    assert len(store.episodic) == before - 1
    assert all("Trivial" not in e["text"] for e in store.episodic)


def test_forget_keeps_default_importance_episodes(store):
    store.add_episode("A normal episode", importance=0.4)
    store.episodic[-1]["ts"] = time.time() - 365 * 86400  # a year old
    # importance 0.4 -> floor of 0.16 salience regardless of age; must survive.
    assert store.forget() == 0
    assert len(store.episodic) == 1


def test_prefs_last_write_wins(store):
    store.set_pref("tone", "formal")
    store.set_pref("tone", "casual")
    assert store.prefs["tone"]["value"] == "casual"
    assert len(store.prefs) == 1


def test_facts_dedupe_identical_text(store):
    store.add_fact("User is allergic to peanuts")
    store.add_fact("User is allergic to peanuts")
    assert len(store.facts) == 1


def test_clamp01_bounds_and_defaults():
    # In-range values (incl. explicit 0 — no falsy footgun) pass through unchanged.
    assert _clamp01(0.5) == 0.5
    assert _clamp01(0.0) == 0.0
    assert _clamp01(1.0) == 1.0
    # Out-of-range (foreign store / raw-percent caller) is bounded to [0, 1].
    assert _clamp01(25) == 1.0
    assert _clamp01(-3) == 0.0
    # Missing / wrong type / bool / non-finite fall back to the supplied default.
    assert _clamp01(None, 0.4) == 0.4
    assert _clamp01("high", 0.4) == 0.4
    assert _clamp01(True, 0.4) == 0.4          # bool is an int subclass, not a weight
    assert _clamp01(float("nan"), 0.4) == 0.4
    assert _clamp01(float("inf"), 0.4) == 0.4


def test_forget_ignores_out_of_range_importance(store):
    # Records loaded from a hand-edited / foreign / migrated store bypass
    # add_episode's clamp, so forget() must bound importance at its own read
    # boundary — it MULTIPLIES importance into the decayed-salience decision.
    now = time.time()
    # Fresh episode, importance=-3: unclamped -> recency*0.6 + (-3)*0.4 < 0, below the
    # floor -> force-forgotten the moment it is written = silent data loss. Must survive.
    store.episodic.append({"text": "fresh but importance=-3", "importance": -3,
                           "ts": now, "emb": [1.0]})
    # Ancient episode, importance=25: unclamped -> 0.6*recency + 25*0.4 ~= 10, never
    # below the floor no matter how decayed -> un-prunable forever (defeats forgetting).
    store.episodic.append({"text": "ancient but importance=25", "importance": 25,
                           "ts": now - 400 * 86400, "emb": [1.0]})

    dropped = store.forget()
    texts = [e["text"] for e in store.episodic]
    assert "fresh but importance=-3" in texts, "fresh episode wrongly force-forgotten"
    # importance=25 clamps to 1.0 -> forget floor 1.0*0.4=0.4 > SALIENCE_FLOOR, so it is
    # retained like any legitimate max-importance episode (bounded, not unbounded).
    assert "ancient but importance=25" in texts
    assert dropped == 0


def test_salience_bounds_out_of_range_importance(store):
    # _salience MULTIPLIES importance in: an unclamped 25 adds 25*0.15=3.75 and lets a
    # junk item outrank a genuinely relevant hit; an unclamped -3 drives a real memory's
    # score down (can sink it below the token budget). Identical text/emb/ts isolates
    # importance as the only difference.
    q = [1.0, 0.0]
    junk = {"text": "junk", "importance": 25,  "ts": time.time(), "emb": [1.0, 0.0]}
    neg  = {"text": "neg",  "importance": -3,  "ts": time.time(), "emb": [1.0, 0.0]}
    ok   = {"text": "ok",   "importance": 1.0, "ts": time.time(), "emb": [1.0, 0.0]}
    # 25 clamps to 1.0 -> ties the legitimate max-importance item (mutation catcher:
    # unclamped, junk scores far higher and this equality fails).
    # approx: each _salience call reads the clock a hair apart (recency differs in the
    # last decimal); an unclamped 25 would score ~3.75 vs ~1.0 and blow past approx.
    assert store._salience(junk, q) == pytest.approx(store._salience(ok, q), abs=1e-4)
    # -3 clamps to 0.0 -> lowest but never negative, and strictly below the real item.
    assert store._salience(neg, q) >= 0.0
    assert store._salience(neg, q) < store._salience(ok, q)


def test_add_persists_clamped_importance(store):
    # add_fact / add_episode also clamp so the on-disk value is canonical.
    store.add_fact("a durable fact", importance=25)
    store.add_episode("an episode summary", importance=-3)
    assert store.facts[-1]["importance"] == 1.0
    assert store.episodic[-1]["importance"] == 0.0
    reloaded = MemoryStore(root=store.root)
    assert reloaded.facts[-1]["importance"] == 1.0
    assert reloaded.episodic[-1]["importance"] == 0.0


def test_persistence_across_store_instances(patched):
    root = str(patched / "persist")
    s1 = MemoryStore(root=root)
    s1.add_fact("The user is allergic to peanuts")
    s1.set_pref("name", "Ben")

    # Brand new instance, same dir — no history replayed, memory reloaded from disk.
    s2 = MemoryStore(root=root)
    assert any("peanut" in f["text"].lower() for f in s2.facts)
    assert s2.prefs["name"]["value"] == "Ben"
