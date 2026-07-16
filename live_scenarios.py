#!/usr/bin/env python3
"""Live edge-case scenario suite for the Aegis MemoryAgent — runs against the REAL
Qwen model (embeddings + chat). Prints a PASS/FAIL report. Needs QWEN_API_KEY.

    QWEN_API_KEY=sk-... python live_scenarios.py
"""
import os, sys, time, tempfile, shutil, traceback
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
from memoryagent.memory import MemoryStore, _now
from memoryagent.agent import MemoryAgent
from memoryagent import config

R = []
def check(name, cond, detail=""):
    R.append((name, bool(cond)))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))

def fresh():
    root = tempfile.mkdtemp(prefix="mem-scn-")
    return MemoryStore(root), root

print(f"config: HALFLIFE={config.DECAY_HALFLIFE_DAYS}d  FLOOR={config.SALIENCE_FLOOR}  "
      f"BUDGET={config.RECALL_TOKEN_BUDGET}  TOP_K={config.RECALL_TOP_K}\n")

print("S1 — Preference last-write-wins")
try:
    s, root = fresh()
    s.set_pref("address", "Ben"); s.set_pref("address", "Chief")
    check("S1a latest value wins", s.prefs["address"]["value"] == "Chief", f"value={s.prefs['address']['value']}")
    check("S1b prefs don't pile up", len(s.prefs) == 1, f"count={len(s.prefs)}")
    shutil.rmtree(root, ignore_errors=True)
    # live end-to-end: teach, override, restart, ask
    s, root = fresh(); a = MemoryAgent(s)
    a.chat("Please call me Ben.")
    a.chat("Actually, from now on call me Chief, not Ben.")
    reply = MemoryAgent(MemoryStore(root)).chat("What should you call me?")
    check("S1c live override survives restart", "chief" in reply.lower(), f"reply={reply.strip()[:60]!r}")
    shutil.rmtree(root, ignore_errors=True)
except Exception as e:
    check("S1 preference", False, f"ERROR {e}"); traceback.print_exc()

print("\nS2 — Decay & prune (facts survive, stale low-salience episodes drop)")
try:
    s, root = fresh()
    s.add_fact("Ben founded Northwind Labs")                      # durable
    s.add_episode("we chatted about the weather", importance=0.02)   # prunable
    s.add_episode("URGENT server-outage postmortem", importance=0.95)  # high-salience control
    old = _now() - 3650 * 86400                                  # age everything ~10 years
    for it in s.episodic: it["ts"] = old
    nf = len(s.facts)
    dropped = s.forget()
    check("S2a stale low-salience episode pruned", dropped >= 1, f"dropped={dropped}")
    check("S2b facts untouched by forget", len(s.facts) == nf, f"facts={len(s.facts)}")
    check("S2c high-importance episode survives", any("URGENT" in e["text"] for e in s.episodic),
          f"left={[e['text'][:18] for e in s.episodic]}")
    shutil.rmtree(root, ignore_errors=True)
except Exception as e:
    check("S2 decay/prune", False, f"ERROR {e}"); traceback.print_exc()

print("\nS3 — Salience ranking with distractors (live embeddings)")
try:
    s, root = fresh()
    s.add_fact("My dog's name is Rex")
    for i in range(12):
        s.add_episode(f"note {i}: quarterly spreadsheet reconciliation and tax filing", importance=0.4)
    picked, _ = s.recall("what is my dog called?", top_k=3)
    texts = [p["text"] for p in picked]
    check("S3 target surfaces in top-3 despite 12 distractors", any("Rex" in t for t in texts),
          f"top3={[t[:22] for t in texts]}")
    shutil.rmtree(root, ignore_errors=True)
except Exception as e:
    check("S3 salience distractors", False, f"ERROR {e}"); traceback.print_exc()

print("\nS4 — Conflicting info (recency resolves)")
try:
    s, root = fresh()
    s.add_fact("I live in Texas"); time.sleep(0.05)
    s.add_fact("I live in California")   # newer, conflicts
    picked, _ = s.recall("where do I live?", top_k=5)
    order = [p["text"] for p in picked]
    tx = next((i for i, t in enumerate(order) if "Texas" in t), 99)
    ca = next((i for i, t in enumerate(order) if "California" in t), 99)
    check("S4 newer conflicting fact ranks above older", ca < tx, f"CA@{ca} TX@{tx}")
    shutil.rmtree(root, ignore_errors=True)
except Exception as e:
    check("S4 conflicting info", False, f"ERROR {e}"); traceback.print_exc()

print("\nS5 — Importance clamp + zero-budget boundary")
try:
    s, root = fresh()
    s.add_fact("clamp-hi", importance=25)
    s.add_fact("clamp-lo", importance=-3)
    imps = [f["importance"] for f in s.facts]
    check("S5a importance clamped to [0,1]", all(0 <= i <= 1 for i in imps), f"importances={imps}")
    check("S5b token_budget=0 returns nothing", len(s.recall("x", token_budget=0)[0]) == 0)
    check("S5c top_k=0 returns nothing", len(s.recall("x", top_k=0)[0]) == 0)
    shutil.rmtree(root, ignore_errors=True)
except Exception as e:
    check("S5 clamp/zero-budget", False, f"ERROR {e}"); traceback.print_exc()

p = sum(1 for _, ok in R if ok); n = len(R)
print(f"\n===== RESULT: {p}/{n} checks passed =====")
sys.exit(0 if p == n else 1)
