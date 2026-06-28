# Security Policy

## Reporting a vulnerability
If you discover a security vulnerability in **Aegis MemoryAgent**, please report it
**privately** — do not open a public issue for an exploitable flaw.

- **Preferred:** open a [GitHub Security Advisory](https://github.com/BenDuske/qwen-memoryagent/security/advisories/new)
  (private disclosure to the maintainer).
- Include: affected version/commit, a description, reproduction steps, and impact.

Please give a reasonable window for a fix before any public disclosure. This is a
volunteer-maintained open-source project; we will acknowledge reports as promptly as we can.

## Scope
This Software is **local-first**: it runs on your machine and stores memory in local files. The
most relevant security considerations are therefore on the **operator** side:

- **API keys** live in your environment / `.env`. Keep that file out of version control
  (`.gitignore` already excludes `.env`) and protect it with OS file permissions.
- **Memory store** (`MEMORY_DIR`) is plain JSONL on disk. It may contain sensitive content you
  fed the agent. Protect it with filesystem permissions and, ideally, disk encryption.
- **Network egress** goes only to the AI provider endpoint you configure. Verify you trust that
  endpoint.

## What is in scope for a report
- Code paths that could leak your API key or memory to an unintended destination.
- Injection, path-traversal, or deserialization issues in the agent, CLI, or HTTP service.
- Dependency vulnerabilities (the project is intentionally dependency-light).

## What is out of scope
- The behavior or content of third-party AI models/providers you configure.
- Misconfiguration of your own OS permissions or your own deployment.
- The inherent fallibility of AI output (see `docs/legal/DISCLAIMER.md`).
