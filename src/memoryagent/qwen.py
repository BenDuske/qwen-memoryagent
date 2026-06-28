"""Qwen Cloud client — chat + embeddings over DashScope's OpenAI-compatible endpoint.

Stdlib only (urllib) so the agent has zero third-party runtime deps. Both calls hit
Alibaba Cloud Model Studio; swap models via env (qwen-plus / qwen-max / qwen-turbo).
"""
import json
import urllib.request
import urllib.error
from . import config


def _post(path: str, payload: dict) -> dict:
    url = config.QWEN_BASE_URL.rstrip("/") + path
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {config.QWEN_API_KEY}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")
        raise RuntimeError(f"Qwen Cloud HTTP {e.code}: {detail}") from None


def chat(messages, model: str = None, temperature: float = 0.4) -> str:
    data = _post("/chat/completions", {
        "model": model or config.CHAT_MODEL,
        "messages": messages,
        "temperature": temperature,
    })
    return data["choices"][0]["message"]["content"]


def embed(texts):
    if isinstance(texts, str):
        texts = [texts]
    data = _post("/embeddings", {"model": config.EMBED_MODEL, "input": texts})
    # responses come back index-ordered
    items = sorted(data["data"], key=lambda d: d.get("index", 0))
    return [it["embedding"] for it in items]
