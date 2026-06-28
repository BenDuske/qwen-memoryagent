# Aegis MemoryAgent — © 2026 Ben Duske. Licensed under the MIT License (see LICENSE).
"""Safety, consent, and ethics layer — stdlib only.

Three responsibilities, all local and dependency-free:

1. BASELINE_POLICY  — the non-negotiable safety rules, prepended to every system prompt.
2. Ethics onboarding — optional org-supplied mission/voice/boundaries layered ABOVE the user
   request but BELOW the baseline (config can tighten, never loosen).
3. Consent gate     — first-run agreement to LICENSE/ToS/AUP/Privacy/Disclaimer, recorded
   locally with a timestamp + policy version.

This is defense-in-depth, not a guarantee: the screen() heuristic catches the most clearly
prohibited requests (zero-tolerance: sexualization of minors), and the BASELINE_POLICY steers
the model. A human stays in the loop for anything consequential (see docs/legal/DISCLAIMER.md).
"""
import os
import re
import time

from . import config

POLICY_VERSION = "2026-06-28"

# --- 1. Baseline safety policy (always on, cannot be overridden by ethics config) ----------
BASELINE_POLICY = (
    "SAFETY POLICY (highest priority, non-negotiable):\n"
    "- Operate only within the law: U.S. federal law and the user's own state and local law. "
    "Where laws differ, follow the most restrictive that applies.\n"
    "- Refuse to produce: sexual content, nudity, or explicit adult role-play; and ALWAYS "
    "refuse, with zero tolerance, anything sexualizing a minor.\n"
    "- Refuse to help with content that enables serious physical harm (weapons of mass harm, "
    "explosives, illicit drug/toxin synthesis), unauthorized intrusion/malware, fraud, "
    "harassment, or privacy violations.\n"
    "- AI output is assistive, not authoritative, and is not professional (legal/medical/"
    "financial) advice. Encourage human verification for consequential decisions.\n"
    "- When a request crosses these lines, briefly refuse and, where possible, offer a safe, "
    "lawful alternative. Do not reveal how to circumvent these rules."
)

# A short, user-facing refusal the caller can surface when screen() hard-blocks.
REFUSAL_MESSAGE = (
    "I can't help with that — it falls outside this assistant's safety policy "
    "(see docs/legal/ACCEPTABLE_USE_POLICY.md). If you rephrase toward a lawful, "
    "non-explicit goal, I'm glad to help."
)

# --- 2. Best-effort input screen --------------------------------------------------------------
# Heuristic only. The model + BASELINE_POLICY are the primary gate; this is a coarse net for the
# most clearly prohibited inputs. ZERO-TOLERANCE category is hard-blocked; others are advisory
# unless STRICT_SCREEN is enabled, to avoid over-refusing legitimate security/research use.
_MINOR_TERMS = r"(child|children|minor|underage|preteen|pre-teen|infant|toddler|kid|kids|\b(?:1[0-7]|[0-9])\s*(?:yo|y/o|year[\s-]?old)s?)"
_SEXUAL_TERMS = r"(sexual|sex\b|nude|naked|porn|explicit|nsfw|erotic|fellatio|genital|aroused)"
_ZERO_TOLERANCE = re.compile(_MINOR_TERMS + r".{0,40}" + _SEXUAL_TERMS, re.I | re.S)
_ZERO_TOLERANCE_REV = re.compile(_SEXUAL_TERMS + r".{0,40}" + _MINOR_TERMS, re.I | re.S)

_STRICT = os.environ.get("AEGIS_STRICT_SCREEN", "") not in ("", "0", "false", "False")
_SEXUAL_ONLY = re.compile(r"\b(porn|nsfw|erotic|sexually explicit|adult role[\s-]?play)\b", re.I)


def screen(text: str):
    """Return (allowed: bool, category: str|None, message: str|None).

    Hard-blocks any apparent sexualization of a minor unconditionally. Other categories are
    flagged (and blocked only under AEGIS_STRICT_SCREEN) so legitimate security/legal/research
    discussion isn't over-refused — the BASELINE_POLICY in the system prompt handles the rest.
    """
    if not text:
        return True, None, None
    if _ZERO_TOLERANCE.search(text) or _ZERO_TOLERANCE_REV.search(text):
        return False, "minor_safety", REFUSAL_MESSAGE
    if _STRICT and _SEXUAL_ONLY.search(text):
        return False, "sexual_content", REFUSAL_MESSAGE
    return True, None, None


# --- 3. Ethics onboarding (optional, layered ABOVE the request, BELOW the baseline) ----------
_ETHICS_KEYS = (
    "organization", "mission", "values", "voice", "goals",
    "boundaries", "required_disclosures",
)


def load_ethics(path: str = None) -> dict:
    """Parse the flat key: value ethics file (a tiny YAML subset; stdlib only)."""
    path = path or os.environ.get("AEGIS_ETHICS_FILE", "")
    if not path or not os.path.exists(path):
        return {}
    out = {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if not line or line.lstrip().startswith("#") or ":" not in line:
                    continue
                key, _, val = line.partition(":")
                key = key.strip().lower()
                if key in _ETHICS_KEYS:
                    out[key] = val.strip().strip('"').strip("'")
    except Exception:
        return {}
    return out


def ethics_preamble(ethics: dict = None) -> str:
    ethics = ethics if ethics is not None else load_ethics()
    if not ethics:
        return ""
    lines = ["ORGANIZATION CONTEXT (applies unless it conflicts with the SAFETY POLICY above):"]
    label = {
        "organization": "Organization", "mission": "Mission", "values": "Values",
        "voice": "Voice/tone", "goals": "Goals", "boundaries": "Boundaries",
        "required_disclosures": "Always disclose",
    }
    for k in _ETHICS_KEYS:
        if ethics.get(k):
            lines.append(f"- {label[k]}: {ethics[k]}")
    return "\n".join(lines)


def system_preamble(persona: str = None) -> str:
    """Baseline safety policy + optional org ethics + persona, in precedence order."""
    persona = persona if persona is not None else config.PERSONA
    blocks = [BASELINE_POLICY]
    eth = ethics_preamble()
    if eth:
        blocks.append(eth)
    blocks.append(persona)
    return "\n\n".join(blocks)


# --- consent gate ----------------------------------------------------------------------------
def _consent_path() -> str:
    return os.path.join(os.path.expanduser(config.MEMORY_DIR), ".consent.json")


def has_consent() -> bool:
    if os.environ.get("AEGIS_ASSUME_CONSENT", "") not in ("", "0", "false", "False"):
        return True
    p = _consent_path()
    if not os.path.exists(p):
        return False
    try:
        import json
        with open(p, "r", encoding="utf-8") as fh:
            return json.load(fh).get("version") == POLICY_VERSION
    except Exception:
        return False


def record_consent() -> None:
    import json
    p = _consent_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump({"version": POLICY_VERSION, "ts": int(time.time()),
                   "agreed": True}, fh)


CONSENT_PROMPT = (
    "\n=== Aegis MemoryAgent — agreement required before first use ===\n"
    "By continuing you agree to the MIT License, Terms of Service, Acceptable Use Policy,\n"
    "Privacy Policy, and AI Output & Warranty Disclaimer (see the repo's LICENSE,\n"
    "CONSENT.md, and docs/legal/). In short:\n"
    "  - Lawful use only (U.S. federal + your state/local law).\n"
    "  - No sexual/explicit content, and zero tolerance for sexualizing minors.\n"
    "  - AI output may be wrong and is NOT professional advice — you verify and decide.\n"
    "  - Provided 'as is', no warranty, at your own risk.\n"
    f"  Policy version: {POLICY_VERSION}\n"
    "Type AGREE to accept, anything else to exit: "
)


def ensure_consent(input_fn=input, output_fn=print) -> bool:
    """Interactive first-run gate. Returns True if consent is (now) on file."""
    if has_consent():
        return True
    try:
        answer = input_fn(CONSENT_PROMPT)
    except (EOFError, KeyboardInterrupt):
        output_fn("\nNo agreement recorded — exiting.")
        return False
    if answer.strip().upper() == "AGREE":
        record_consent()
        output_fn("Agreement recorded. Welcome to Aegis.\n")
        return True
    output_fn("You did not agree — exiting. (Nothing was changed.)")
    return False
