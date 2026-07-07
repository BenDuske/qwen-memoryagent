#!/usr/bin/env python3
"""Non-interactive proof of cross-session memory (the Track-1 point).

Session 1 teaches the agent a few things. We then throw the agent away and build a
FRESH one over the SAME on-disk store (simulating a process restart / new session) —
with NO conversation history replayed — and show it still knows them.

    QWEN_API_KEY=sk-... python demo.py
"""
import os
import sys
import shutil
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
from memoryagent import config
from memoryagent.agent import MemoryAgent
from memoryagent.memory import MemoryStore

# This demo makes LIVE Qwen Cloud chat calls. Without a key the very first turn
# blocks on the network until urllib's 120s timeout, then dies with a raw
# RuntimeError — fail fast with a clear instruction instead, and point at the
# fully keyless recall proof (eval.py) for anyone who just wants to see the point.
if not config.QWEN_API_KEY:
    sys.exit(
        "demo.py needs a Qwen Cloud API key — it makes live chat calls.\n"
        "  export QWEN_API_KEY=sk-...      # or DASHSCOPE_API_KEY\n"
        "  python demo.py\n"
        "No key? See the memory engine work with zero network:  python eval.py"
    )

root = tempfile.mkdtemp(prefix="memoryagent-demo-")
try:
    print("=== SESSION 1 — teach the agent ===")
    a1 = MemoryAgent(MemoryStore(root))
    for u in [
        "Hi, I'm Ben. Always call me Ben, never 'Commander'.",
        "I run a company called Northwind Labs — a privacy-first robotics startup.",
        "I like concise, direct answers with no fluff.",
    ]:
        print("you>  ", u)
        print("aegis>", a1.chat(u), "\n")

    print("=== RESTART — brand-new agent over the same store (no history replay) ===")
    a2 = MemoryAgent(MemoryStore(root))
    print("memory loaded from disk:", a2.mem.stats(), "\n")
    for q in [
        "What's my company, and what's it about?",
        "What should you call me?",
    ]:
        print("you>  ", q)
        print("aegis>", a2.chat(q), "\n")
finally:
    shutil.rmtree(root, ignore_errors=True)
