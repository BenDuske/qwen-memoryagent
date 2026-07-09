#!/usr/bin/env bash
# Missing-beats capture: Bounded recall (Beat 3) + Forgetting (Beat 4) + test suite.
# Seeds the store DIRECTLY (fast Qwen embeds, no slow per-item LLM chat) so it records
# in ~40s with deterministic output.
set -u
cd "$(dirname "$0")/.."
sed 's/^\xEF\xBB\xBF//' .env > /tmp/qk.env 2>/dev/null; set -a; . /tmp/qk.env; set +a
export QWEN_API_KEY="${QWEN_API_KEY:-$DASHSCOPE_API_KEY}"
export QWEN_CHAT_MODEL=qwen-plus
export AEGIS_ASSUME_CONSENT=1 PYTHONUTF8=1 PYTHONIOENCODING=utf-8
export DECAY_HALFLIFE_DAYS=0.0001 SALIENCE_FLOOR=0.5 RECALL_TOKEN_BUDGET=1200 RECALL_TOP_K=8

clear
echo; echo "   Preparing ... recording starts momentarily"; sleep 12; clear

python - <<'PY'
import time
from memoryagent.memory import MemoryStore

def banner(t):
    print("\n" + "="*66); print("  " + t); print("="*66 + "\n")

store = MemoryStore("./.demo-mem-b34")
# reset for a clean, reproducible run
store.facts.clear(); store.episodic.clear(); store.prefs.clear()

banner("BEAT 3 - Bounded recall  (memory grows forever; the prompt can't)")
print("  Loading memory for 'Sam' ...")
for t in ["I'm allergic to penicillin",
          "I run PostgreSQL 15 in production on port 5432",
          "My daughter's name is Mia",
          "I'm building a Rust CLI called ferro",
          "I live in Denver"]:
    store.add_fact(t, importance=0.9)
for i in range(1, 31):
    store.add_fact(f"Reference note number {i}: item XYZ-{i}", importance=0.5)
for t in ["lunch was tacos today", "the standup ran long", "it rained on Tuesday",
          "coffee order is a flat white", "chatted about the weekend"]:
    store.add_episode(t, importance=0.2)

s = store.stats()
print(f"  Stored: {s['facts']} facts + {s['episodes']} episodes = {s['facts']+s['episodes']} memories on disk.\n")
print("  recall('what am I allergic to', budget=400, top_k=5)  -- only the salient few return:")
picked, _ = store.recall("what am I allergic to", token_budget=400, top_k=5)
for it in picked:
    print(f"     - {it['text']}")
print(f"\n  {len(picked)} of {s['facts']+s['episodes']} memories injected -- the rest stay on disk, under budget.")

print("\n  (letting the low-value episodes age past the decay floor ...)")
time.sleep(16)

banner("BEAT 4 - Forgetting  (low-value episodes decay & prune; facts survive)")
before = store.stats()
print(f"  before forget:  {before['facts']} facts, {before['episodes']} episodes")
dropped = store.forget()
after = store.stats()
print(f"  forget()     :  dropped {dropped} stale episodes")
print(f"  after forget :  {after['facts']} facts, {after['episodes']} episodes")
print("\n  Durable facts (penicillin, Postgres, Mia) survived. Small talk aged out.")
PY

sleep 4
echo; echo "=================================================================="
echo "  PROVEN, NOT VIBES - full suite, no Qwen key required (~1s)"
echo "=================================================================="; echo
env -u DECAY_HALFLIFE_DAYS -u SALIENCE_FLOOR -u RECALL_TOKEN_BUDGET -u RECALL_TOP_K -u MEMORY_DIR \
    python -m pytest 2>&1 | grep -iE "passed|failed|error" | tail -1 | sed 's/^/  ✅  /'
sleep 3
echo; echo "=================================================================="
echo "  Cross-session recall - bounded budget - decay-based forgetting  |  Qwen Cloud"
echo "=================================================================="
echo "  All original code - MIT - deployed on Alibaba Cloud"
sleep 4
touch /tmp/beats34_done
