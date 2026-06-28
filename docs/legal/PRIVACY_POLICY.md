# Privacy Policy

> **DRAFT — pending attorney review.** Provided in good faith for the open-source release;
> **not legal advice.** A commercial operator must have counsel review and adapt this before
> relying on it.

**Software:** Aegis MemoryAgent ("the Software").
**Last updated:** 2026-06-28.

This policy describes how the **open-source Software** handles data. If you obtained the
Software from a third party who runs it as a hosted service, **their** privacy policy governs
that service — ask them.

## 1. The short version
The Software is **local-first**. The memory store is plain files on **your own machine**. The
author of the Software operates **no servers**, collects **no telemetry**, and never receives
your data. The only data that leaves your machine is what you choose to send to the AI
provider you configure (by default, **Qwen Cloud / Alibaba Cloud Model Studio**) to get
responses and embeddings.

## 2. What data is involved
- **Your inputs and memories.** Messages, facts, and preferences you give the agent are stored
  as JSONL + a local vector index in your configured `MEMORY_DIR`. They stay on your machine.
- **Your API key.** Read from your environment / `.env`. It is used only to authenticate to
  your AI provider. It is never transmitted anywhere else and is not logged.
- **Network calls to your AI provider.** To answer you, the Software sends your prompt and the
  recalled memory context to the provider's API and receives a completion / embeddings. That
  provider processes this data under **its own** privacy terms and model terms.

## 3. What the author collects
**Nothing.** No analytics, no telemetry, no crash reporting, no "phone home." You can verify
this — the source is open and dependency-light (standard library at runtime).

## 4. Third-party processors you choose
- **Qwen Cloud / Alibaba Cloud Model Studio (DashScope)** — default chat + embeddings. Your
  prompts and memory context are sent here. Review Alibaba Cloud's privacy and data-usage
  terms. You may point the Software at any other OpenAI-compatible endpoint (including a fully
  local model), in which case **that** provider's terms apply instead.

## 5. Your control over your data
Because storage is local files you own:
- **Access / export:** read the JSONL directly.
- **Delete:** use the agent's `forget` operation, or delete the `MEMORY_DIR`. Deletion is
  immediate and permanent; there is no backup the author holds.
- **Portability:** the store is open JSONL — copy it anywhere.

## 6. Children's privacy
The Software is **not directed to children under 13** (or the minimum age of digital consent
in your jurisdiction). Do not use it to knowingly collect data from children, and never to
process content sexualizing minors (see `ACCEPTABLE_USE_POLICY.md`).

## 7. Security
See `SECURITY.md`. In brief: keep your API key and `MEMORY_DIR` protected with your operating
system's file permissions and disk encryption; the Software does not add its own encryption
layer to the local store.

## 8. Changes
Material changes to this policy will be noted in the repository's history. The "Last updated"
date above reflects the current version.

## 9. Contact
Open-source inquiries: via the GitHub repository's issues. Author: **Ben Duske**.
