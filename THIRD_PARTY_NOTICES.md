# Third-Party Notices — Aegis MemoryAgent

This project is MIT-licensed (see `LICENSE`). It is intentionally **dependency-light**.

## Runtime
- **Python standard library only** (no third-party runtime packages). The Qwen Cloud client
  uses `urllib` from the stdlib. → no third-party runtime licenses to bundle.

## External services (not bundled; used via network API)
- **Qwen Cloud / Alibaba Cloud Model Studio (DashScope)** — chat (`qwen3.7-plus`) + embeddings
  (`text-embedding-v4`). Use is governed by the Qwen Cloud / Alibaba Cloud terms and the model
  licenses (Qwen models are released under their respective licenses, e.g. Apache-2.0 for the
  open Qwen series). You bring your own API key; usage is billed to your account.

## Development / optional extras (not required to run the core)
| Component | Used for | License |
|-----------|----------|---------|
| pytest | tests | MIT |
| FastAPI | optional HTTP service (`[service]` extra) | MIT |
| uvicorn | optional ASGI server | BSD-3-Clause |

All of the above are permissive (MIT / BSD / Apache-2.0) and compatible with this project's MIT license.
If any further dependency is added, record it here with its license before release.
