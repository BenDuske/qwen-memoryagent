# Ethics Onboarding — Make the Agent Yours

Aegis MemoryAgent ships with a **baseline safety policy** (no illegal use, no sexual/abusive
content — see `docs/legal/ACCEPTABLE_USE_POLICY.md`) that is always on and cannot be disabled.

On top of that baseline, a business or individual can **layer in their own ethics, mission,
and boundaries** so the agent speaks and acts in line with the organization deploying it. This
is the "onboarding" step.

## How it works
Create an `ethics.yaml` (copy `ethics.example.yaml`) describing your organization. At startup
the agent loads it and **prepends it to the system prompt**, after the baseline safety policy
and before the user's request. Order of precedence (highest first):

1. **Baseline safety policy** (built in — cannot be overridden by config)
2. **Your organization's ethics & boundaries** (`ethics.yaml`)
3. **Learned user preferences** (the memory store)
4. **The current request**

So your mission and tone shape every answer, but **nothing in your config can loosen the
baseline safety rules** — config can only make the agent *more* restrictive or more specific,
never less safe.

## What you can set
- `organization` — name, mission, values, voice/tone.
- `goals` — what the agent should help users accomplish.
- `boundaries` — topics to avoid, disclaimers to always include, escalation rules
  ("for billing questions, direct to a human").
- `required_disclosures` — text the agent must include in relevant answers (e.g. "not financial
  advice"). Useful for regulated industries.

## Example
See [`../ethics.example.yaml`](../ethics.example.yaml). Point the agent at your file with:

```bash
export AEGIS_ETHICS_FILE=./ethics.yaml
```

If no file is set, only the baseline safety policy applies.

## A note on limits
This steers a probabilistic model; it is **strong guidance, not a hard guarantee**. Keep a
human in the loop for high-stakes use, and keep your `required_disclosures` legally reviewed.
