"""The turn loop: recall -> answer (Qwen Cloud) -> extract new memory -> forget."""
import json
from . import config, qwen
from .memory import MemoryStore

_EXTRACT_SYS = (
    "You extract durable memory from a user/assistant exchange. Reply with STRICT JSON only:\n"
    '{"facts": ["..."], "prefs": {"key": "value"}, "episode": "one short summary"}\n'
    "facts = stable truths about the user or their world worth remembering long-term; "
    "prefs = how they want to be served (name, tone, boundaries, habits); "
    "episode = a one-sentence summary of THIS exchange. Omit anything empty. JSON only, no prose."
)


class MemoryAgent:
    def __init__(self, store: MemoryStore = None):
        self.mem = store or MemoryStore()

    def _build_system(self, picked, prefs) -> str:
        parts = [config.PERSONA]
        if prefs:
            parts.append("Known preferences: " +
                         "; ".join(f"{k}={v['value']}" for k, v in prefs.items()))
        if picked:
            parts.append("Relevant memory (recalled):\n- " +
                         "\n- ".join(p["text"] for p in picked))
        return "\n\n".join(parts)

    def chat(self, user_text: str) -> str:
        picked, prefs = self.mem.recall(user_text)
        system = self._build_system(picked, prefs)
        reply = qwen.chat([
            {"role": "system", "content": system},
            {"role": "user", "content": user_text},
        ])
        self._learn(user_text, reply)
        return reply

    def _learn(self, user_text: str, reply: str):
        try:
            raw = qwen.chat(
                [{"role": "system", "content": _EXTRACT_SYS},
                 {"role": "user", "content": f"USER: {user_text}\nASSISTANT: {reply}"}],
                temperature=0,
            )
            data = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        except Exception:
            data = {}
        for fact in data.get("facts", []) or []:
            self.mem.add_fact(fact)
        for k, v in (data.get("prefs", {}) or {}).items():
            self.mem.set_pref(k, v)
        episode = data.get("episode")
        if episode:
            self.mem.add_episode(episode)
        self.mem.forget()
