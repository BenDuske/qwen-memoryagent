# Proof of Deployment on Alibaba Cloud (hackathon eligibility)

**Why:** Devpost/Qwen Cloud requires proof the agent **ran on Alibaba Cloud infrastructure** (not just calling the
API locally). Deliverable = a **screenshot of the ECS/Simple Application Server Workbench** showing this agent
running on the instance. This is the fastest, cheapest path.

> Do this **before Jul 9** — submission closes Jul 9 @ 5PM EDT, and the DashScope key expires ~Jul 9.

---

## 1. Create the instance (cheapest that works)
- Alibaba Cloud Console → **Simple Application Server** (simplest) *or* **ECS** (pay-as-you-go, tiny instance).
- Image: **Ubuntu 22.04** (or Alibaba Cloud Linux). Smallest size is fine (1 vCPU / 1–2 GB).
- **Region:** pick an **international** region (e.g. Singapore `ap-southeast-1`) so the `dashscope-intl` endpoint
  matches. *(If you use a mainland region, switch the base URL to `https://dashscope.aliyuncs.com/compatible-mode/v1`.)*

## 2. Open the Workbench (this is what you'll screenshot)
- On the instance card → **Connect** → **Workbench** (the browser-based terminal in the Alibaba console).

## 3. Deploy + run the agent (paste into the Workbench terminal)
```bash
sudo apt update && sudo apt install -y python3-pip git
git clone https://github.com/BenDuske/qwen-memoryagent
cd qwen-memoryagent
pip install -e .          # Option A (demo.py) — core is stdlib-only, this is all it needs
# For Option B (the HTTP service) you ALSO need fastapi+uvicorn, which live in an extra:
#   pip install -e '.[service]'
# (if -e errors on this box: pip install '.[service]'  then prefix runs with  PYTHONPATH=src )

# Qwen Cloud credentials (paste your real DashScope key):
export QWEN_API_KEY=sk-YOUR_REAL_DASHSCOPE_KEY
export QWEN_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
```

Now run it — **two options, either makes a great screenshot:**

**Option A — the cross-session memory demo (clear, self-explaining output):**
```bash
python demo.py
```

**Option B — the live HTTP service, then hit it from the same box:**
```bash
pip install -e '.[service]'   # installs fastapi + uvicorn (skip if you already did it above)
python -m uvicorn memoryagent.app:app --host 0.0.0.0 --port 8000 &
sleep 3
curl -s localhost:8000/healthz    # health endpoint is /healthz — returns {"ok":true,...}
```
Tip: for an even stronger visual, open **`http://<instance-public-ip>:8000/docs`** in a browser — the
FastAPI Swagger UI renders the live endpoint list, which reads more clearly as "a running app" than a
one-line JSON response. (Requires the instance security group to allow inbound TCP 8000.) The `/healthz`
curl alone is fully sufficient proof; `/docs` is optional polish.

## 4. Take the screenshot ✅
Capture the **Workbench** with, clearly visible in one frame:
- the **Alibaba Cloud console chrome / instance context** (so it's obviously *their* Workbench, not a local terminal), and
- the **agent running** — the `demo.py` output (Option A) or `uvicorn ... Application startup complete` + the `curl`
  response (Option B).

That single image is the "Proof of Deployment." Add it to the Devpost submission's Proof-of-Deployment field.

## 5. Tidy up
- Stop/release the instance afterward so it stops billing (Simple Application Server can be reset/released; ECS can be stopped).

---
### Notes
- The agent's backend is **100% Qwen Cloud** (DashScope OpenAI-compatible) — base URL is already visible in
  `.env.example`, `DEPLOY.md`, and the blog, satisfying the "code file with the Base URL" requirement.
- No secrets are committed; the key is supplied at runtime via the env var above.
