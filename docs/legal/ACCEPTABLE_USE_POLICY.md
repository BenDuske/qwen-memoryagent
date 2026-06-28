# Acceptable Use Policy (AUP)

> **DRAFT — pending attorney review.** This document is provided as a good-faith policy for
> the open-source release. It is **not legal advice** and has not been reviewed by counsel.
> Operators who deploy this software commercially should have their own attorney review and
> adapt it.

**Applies to:** Aegis MemoryAgent ("the Software"), as distributed at
`https://github.com/BenDuske/qwen-memoryagent`.
**Last updated:** 2026-06-28.

By installing, running, or building on the Software you agree to this Acceptable Use Policy.
If you operate the Software as a service for others, you are responsible for enforcing an
equivalent policy on your own users.

## 1. Lawful use only
You may not use the Software to engage in, facilitate, or encourage any activity that is
unlawful under:
- the laws and regulations of the **United States** (federal), **and**
- the laws and regulations of **your own state, province, and locality**, **and**
- any other jurisdiction whose laws apply to you or to the people you serve.

Where these differ, the **most restrictive applicable law governs**. You — not the author —
are responsible for knowing and following the law that applies where you are.

## 2. Prohibited content and conduct
You may not use the Software to generate, store, request, or distribute:

1. **Child sexual abuse material (CSAM) or any sexualization of minors** — zero tolerance,
   no exceptions. This is reported and blocked at the policy layer and must never be bypassed.
2. **Nudity or sexually explicit content.**
3. **Explicit adult sexual role-play** or sexual content involving real or simulated persons.
4. **Content that facilitates serious physical harm** — instructions for weapons capable of
   mass casualties, explosives, or the synthesis of illegal/controlled substances or toxins.
5. **Unauthorized intrusion or attack** — malware, ransomware, credential theft, or attacks
   on systems you do not own or have explicit written permission to test.
6. **Fraud, deception, or impersonation** — scams, phishing, forged identity, or
   misrepresenting AI output as human where disclosure is legally required.
7. **Harassment, hate, or threats** targeting individuals or protected groups.
8. **Privacy violations** — scraping, doxxing, or processing others' personal data without a
   lawful basis and the disclosures their jurisdiction requires.
9. **Infringement** of intellectual-property, contractual, or trade-secret rights.

## 3. High-stakes use
The Software's AI output is **assistive, not authoritative** (see `DISCLAIMER.md`). Do not
rely on it as the sole basis for **medical, legal, financial, employment, housing, credit,
insurance, or safety-critical** decisions. A qualified human must review and own any such
decision.

## 4. Operator responsibilities (if you deploy it for others)
- Surface this AUP and the `DISCLAIMER` to your end users before they use your deployment.
- Keep your API keys and any stored memory secured; you are the data controller for data your
  users put into the Software.
- Honor applicable data-subject rights (access, deletion) — the memory store is local JSONL,
  so deletion is supported by design (`forget` / removing the store).

## 5. Enforcement
This is open-source software under the MIT License; there is no central operator who can
suspend your local install. Enforcement of this AUP rests with **you** as the operator and
with **the laws that apply to you**. Violations may expose you to civil and criminal
liability for which you alone are responsible. The author disclaims all liability for misuse
(see `TERMS_OF_SERVICE.md` and `DISCLAIMER.md`).

## 6. Reporting abuse
Suspected CSAM or imminent threats to life should be reported to the appropriate authorities
(in the U.S., the NCMEC CyberTipline at report.cybertip.org and/or local law enforcement),
**not** to this repository. Security vulnerabilities: see `SECURITY.md`.
