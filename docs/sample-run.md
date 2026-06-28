# Live cross-session run — Qwen Cloud

Real run against **Qwen Cloud** (`qwen3.7-plus` + `text-embedding-v4`), 2026-06-28.
The agent in **Session 2 is a brand-new process over the same on-disk store** — with **no
conversation history replayed** — yet it recalls what it learned in Session 1. That cross-session
recall (from a managed memory store, not a giant replayed transcript) is the Track-1 point.

```
=== SESSION 1 — teach the agent ===
you>   Hi, I'm Ben. Always call me Ben, never 'Commander'.
aegis> Hi Ben. I'm Aegis. I've updated my memory with your preferences: I will always call you
       Ben and never refer to you as "Commander."

you>   I run a company called Northwind Labs — a privacy-first robotics startup.
aegis> That sounds like a fantastic mission, Ben. Privacy-first robotics is an
       incredibly important space right now...

you>   I like concise, direct answers with no fluff.
aegis> Understood, Ben.

=== RESTART — brand-new agent over the same store (no history replay) ===
memory loaded from disk: { facts: 5, episodes: 3, prefs: 3 }

you>   What's my company, and what's it about?
aegis> Your company is Northwind Labs. It is a privacy-first robotics startup.

you>   What should you call me?
aegis> Ben.
```

Reproduce: `QWEN_API_KEY=sk-... python demo.py`
