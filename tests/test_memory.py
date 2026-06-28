"""MemoryStore: recall ranking, bounded token budget, forgetting, prefs, dedup."""
import time

from memoryagent import config
from memoryagent.memory import MemoryStore, _approx_tokens


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


def test_recall_top_k_caps_count(store):
    for i in range(20):
        store.add_fact(f"hiking fact {i} mountains trails forests")
    picked, _ = store.recall("hiking mountains", token_budget=100000, top_k=5)
    assert len(picked) <= 5


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


def test_persistence_across_store_instances(patched):
    root = str(patched / "persist")
    s1 = MemoryStore(root=root)
    s1.add_fact("The user is allergic to peanuts")
    s1.set_pref("name", "Ben")

    # Brand new instance, same dir — no history replayed, memory reloaded from disk.
    s2 = MemoryStore(root=root)
    assert any("peanut" in f["text"].lower() for f in s2.facts)
    assert s2.prefs["name"]["value"] == "Ben"
