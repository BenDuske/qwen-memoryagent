# Aegis MemoryAgent — © 2026 Ben Duske. Licensed under the MIT License (see LICENSE).
"""The turn loop: screen -> recall -> answer (Qwen Cloud) -> extract new memory -> forget."""
import json
from . import config, qwen, policy
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
        # Safety policy first (non-negotiable), then optional org ethics, then persona.
        parts = [policy.system_preamble()]
        if prefs:
            parts.append("Known preferences: " +
                         "; ".join(f"{k}={v['value']}" for k, v in prefs.items()))
        if picked:
            parts.append("Relevant memory (recalled):\n- " +
                         "\n- ".join(p["text"] for p in picked))
        return "\n\n".join(parts)

    def chat(self, user_text: str) -> str:
        allowed, _cat, refusal = policy.screen(user_text)
        if not allowed:
            return refusal
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
        if not isinstance(data, dict):
            data = {}
        # _learn is best-effort background enrichment and runs AFTER the reply is
        # produced, so NOTHING here may crash the turn and lose an answer the user
        # already earned. Two distinct failure modes are guarded:
        #  1. TYPE: the extractor is untrusted LLM JSON that can PARSE cleanly yet
        #     carry the wrong types (a fact holding a dict, prefs as a list, a
        #     non-string episode) — the isinstance checks skip those, keeping the
        #     valid items in a mixed list.
        #  2. TRANSPORT/IO: add_fact/add_episode each make a live qwen.embed HTTP
        #     call, and every write touches disk — a transient Qwen Cloud failure
        #     (429/500/network blip) or a disk error would otherwise propagate out
        #     of chat() and discard the already-generated reply. _safe isolates each
        #     write so one failure neither crashes the turn nor drops the others.
        facts = data.get("facts")
        if isinstance(facts, list):
            for fact in facts:
                if isinstance(fact, str):
                    self._safe(self.mem.add_fact, fact)
        prefs = data.get("prefs")
        if isinstance(prefs, dict):
            for k, v in prefs.items():
                # Guard the pref VALUE, not just the {prefs:...} container. set_pref
                # wraps v as {"value": v} and _build_system renders f"{k}={v['value']}"
                # into EVERY future system prompt — so a non-string value from the
                # untrusted extractor (a dict/list/number that parsed cleanly) would
                # persist and bake a Python-repr'd blob (name={'first': 'Ben'}) into
                # the prompt forever, degrading answers. Mirror the fact/episode guards
                # above: only store a string value; skip anything else.
                if isinstance(k, str) and isinstance(v, str):
                    self._safe(self.mem.set_pref, k, v)
        episode = data.get("episode")
        if isinstance(episode, str):
            self._safe(self.mem.add_episode, episode)
        self._safe(self.mem.forget)

    @staticmethod
    def _safe(fn, *args):
        # Run a best-effort enrichment write, swallowing any failure. Learning must
        # never surface an error to the turn; a lost memory write is acceptable, a
        # lost reply is not. The next turn re-attempts enrichment from fresh input.
        try:
            fn(*args)
        except Exception:
            pass
