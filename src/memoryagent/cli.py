"""Interactive demo. Memory persists across runs — quit, restart, and it still knows you.
That cross-session recall (without replaying history) is the Track-1 point.
"""
from .agent import MemoryAgent
from . import policy


def main():
    if not policy.ensure_consent():
        return
    agent = MemoryAgent()
    s = agent.mem.stats()
    print("Aegis MemoryAgent — Qwen Cloud (Track 1). Memory persists across sessions.")
    print(f"  loaded: {s['facts']} facts · {s['episodes']} episodes · {s['prefs']} prefs  ({s['dir']})")
    print("  Ctrl-C / Ctrl-D to exit.\n")
    while True:
        try:
            user = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nMemory saved. Bye.")
            break
        if not user:
            continue
        try:
            print("aegis>", agent.chat(user), "\n")
        except Exception as e:
            print(f"[error] {e}\n")


if __name__ == "__main__":
    main()
