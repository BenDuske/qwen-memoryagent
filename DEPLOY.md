# DEPLOY — Aegis MemoryAgent on Alibaba Cloud

This agent is **built on Qwen Cloud** (DashScope / Model Studio, OpenAI-compatible
endpoints) and is designed to **deploy on Alibaba Cloud**. The runtime is stdlib-only
(chat + embeddings go over `urllib`), so the container is tiny and starts cold fast.
The HTTP face is `memoryagent.app:app` (FastAPI); the same memory engine also runs as
an interactive CLI (`python -m memoryagent.cli`).

The one thing that must persist is **`MEMORY_DIR`** — that is where cross-session
memory lives. Mount it on a persistent volume (NAS / disk) or the agent forgets
everything on restart, which defeats the point of Track 1.

## 0. Credentials (Qwen Cloud / DashScope)

Get an API key from Alibaba Cloud **Model Studio** (DashScope). The agent reads:

| Env | Default | Notes |
|-----|---------|-------|
| `QWEN_API_KEY` / `DASHSCOPE_API_KEY` | — | **required** |
| `QWEN_BASE_URL` | `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` | use the CN endpoint inside mainland regions |
| `QWEN_CHAT_MODEL` | `qwen3.7-plus` | `qwen-max` / `qwen-turbo` |
| `QWEN_EMBED_MODEL` | `text-embedding-v4` | |
| `MEMORY_DIR` | `~/.aegis-memoryagent` | **mount this on a persistent volume** |
| `RECALL_TOKEN_BUDGET` | `1200` | bounded-recall ceiling |
| `DECAY_HALFLIFE_DAYS` / `SALIENCE_FLOOR` | `14` / `0.12` | forgetting tunables |

> CN-region endpoint: `https://dashscope.aliyuncs.com/compatible-mode/v1`.

> **Model IDs verified current** against the official Alibaba Cloud Model Studio
> *DashScope API reference* (updated 2026-06-24) and *OpenAI-compatible — Chat*
> guide (updated 2026-06-25): `qwen3.7-plus` and `text-embedding-v4` are live
> Model Studio model IDs reachable over the OpenAI-compatible `/chat/completions`
> and `/embeddings` paths. Swap to `qwen-max` / `qwen-turbo` via `QWEN_CHAT_MODEL`
> with no code change.

## 1. Container build (the deployable artifact)

The `Dockerfile` defaults to the CLI. For the service, run uvicorn against the same image:

```bash
docker build -t aegis-memoryagent:0.1.0 .

docker run --rm -p 8000:8000 \
  -e QWEN_API_KEY=sk-xxxx \
  -e MEMORY_DIR=/data/memory \
  -v aegis_mem:/data \
  aegis-memoryagent:0.1.0 \
  python -m uvicorn memoryagent.app:app --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl localhost:8000/healthz
# {"ok": true, "memory_dir": "/data/memory", "chat_model": "qwen3.7-plus"}
```

Push to **Alibaba Cloud Container Registry (ACR)**:

```bash
docker tag aegis-memoryagent:0.1.0 \
  registry-intl.<region>.aliyuncs.com/<namespace>/aegis-memoryagent:0.1.0
docker push registry-intl.<region>.aliyuncs.com/<namespace>/aegis-memoryagent:0.1.0
```

## 2. Option A — Function Compute (serverless, recommended)

Alibaba Cloud **Function Compute** runs the container directly and scales to zero.

1. Create a **Web Function** → *Custom Container* → point at the ACR image above.
2. Listen port `8000`; set the start command to the uvicorn line from §1.
3. Environment variables: `QWEN_API_KEY`, `QWEN_BASE_URL`, `MEMORY_DIR=/mnt/mem`.
4. **Mount NAS** at `/mnt/mem` so memory survives across invocations and instances
   (Function Compute → NAS integration). Without this, recall is per-instance only.
5. Bind a custom domain / use the generated HTTP trigger URL.

```bash
# fcli / serverless-devs sketch (s.yaml):
#   triggers: http (GET/POST, anonymous or jwt)
#   nasConfig: mountDir /mnt/mem  ->  your NAS file system
#   environmentVariables: { QWEN_API_KEY, MEMORY_DIR: /mnt/mem }
```

## 3. Option B — ECS (always-on VM)

```bash
# on an ECS instance (Ubuntu/Alibaba Cloud Linux) with Docker:
docker run -d --restart=always -p 80:8000 \
  -e QWEN_API_KEY=sk-xxxx -e MEMORY_DIR=/data/memory \
  -v /opt/aegis/data:/data \
  registry-intl.<region>.aliyuncs.com/<namespace>/aegis-memoryagent:0.1.0 \
  python -m uvicorn memoryagent.app:app --host 0.0.0.0 --port 8000
```

Put it behind **SLB / ALB** for TLS + health checks (`/healthz`). `/opt/aegis/data`
should be a mounted cloud disk so memory is durable.

## 4. Smoke test the live deployment

```bash
BASE=https://<your-deployment>

# turn 1 — teach it something
curl -s $BASE/chat -H 'content-type: application/json' \
  -d '{"user":"ben","text":"I am allergic to peanuts and prefer to be called Ben"}'

# turn 2 — a NEW request (new session). It recalls without replaying history:
curl -s $BASE/chat -H 'content-type: application/json' \
  -d '{"user":"ben","text":"suggest a snack for my flight"}'

# inspect bounded recall directly (what would be injected, at what token cost):
curl -s "$BASE/memory/ben/recall?q=snack%20allergy&budget=1200"

# trigger forgetting:
curl -s -X POST $BASE/memory/ben/forget
```

The Track-1 proof is in turn 2: the second request is a fresh HTTP call with no
history attached, yet the reply respects the peanut allergy — because memory was
**recalled from the store**, not pasted from a transcript, and only the highest-salience
memories within `RECALL_TOKEN_BUDGET` were injected.

A captured live run that goes one step further — teaching over one process, **fully
restarting the service**, then recalling over a second process on the same `MEMORY_DIR`
— is in [`docs/transcripts/live-http-service-demo.md`](docs/transcripts/live-http-service-demo.md)
(regenerate with `python scripts/live_http_demo.py`). It demonstrates the memory survives
a real container restart, which is exactly why `MEMORY_DIR` must be a persistent volume.

## 5. Cost / scaling notes
- Embeddings are cached on disk inside each memory item (`emb`), so re-recall costs
  no Qwen calls — only *new* facts/episodes embed.
- Recall is O(n) cosine over a bounded store; forgetting keeps `n` from growing
  unbounded. For very large user bases, shard `MEMORY_DIR` per user (the app already
  roots each user's store separately) or swap the JSONL index for a vector DB.
- Function Compute scales to zero between users — you pay only for active turns.
