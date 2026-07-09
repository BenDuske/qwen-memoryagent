#!/usr/bin/env bash
# Aegis MemoryAgent — recorded demo player (Track 1, Qwen Cloud).
# Runs every terminal beat deterministically with readable pacing so it can be
# screen-recorded in one pass. Narration (Ben-clone) is laid over in edit.
set -u
cd "$(dirname "$0")/.."

# --- demo environment (validated off-camera 2026-07-09) ---
sed 's/^\xEF\xBB\xBF//' .env > /tmp/qk.env 2>/dev/null; set -a; . /tmp/qk.env; set +a
export QWEN_API_KEY="${QWEN_API_KEY:-$DASHSCOPE_API_KEY}"
export QWEN_CHAT_MODEL=qwen-plus          # fast model for on-camera pacing
export MEMORY_DIR="./.demo-mem"
export AEGIS_ASSUME_CONSENT=1             # consent shown as its own clip; avoid stdin desync
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8 # render emoji instead of crashing the console
export DECAY_HALFLIFE_DAYS=0.0001 SALIENCE_FLOOR=0.5  # make forgetting visible on camera
export RECALL_TOKEN_BUDGET=1200 RECALL_TOP_K=8

pause(){ sleep "${1:-2}"; }
banner(){ echo; echo "=================================================================="; echo "  $1"; echo "=================================================================="; echo; }

rm -rf ./.demo-mem
clear
echo; echo "   Preparing demo — recording starts momentarily ..."; sleep 14
clear
banner "AEGIS MEMORYAGENT  —  Qwen Cloud  —  Track 1"
echo "  Cross-session recall · bounded by a token budget · decay-based forgetting"
pause 3

banner "BEAT 1 — Teaching the agent (durable memory, not a replayed transcript)"
cat > /tmp/teach.txt <<'EOF'
Hi, I'm Sam. I'm allergic to penicillin.
I run PostgreSQL 15 in production on port 5432.
My daughter's name is Mia.
I'm building a Rust CLI called ferro.
I live in Denver.
Keep your answers short and blunt.
Use metric units.
Lunch was tacos today.
The standup ran long this morning.
It rained here on Tuesday.
By the way, my coffee order is a flat white.
Actually, switch to imperial units, not metric.
EOF
echo "Feeding the agent (each line embeds via Qwen Cloud and is stored to disk):"; echo
while IFS= read -r line; do echo "  you> $line"; done < /tmp/teach.txt
echo; echo "  ... running live through Qwen Cloud ..."; echo
python -m memoryagent.cli < /tmp/teach.txt 2>&1 | sed 's/^/  /'
pause 3

banner "PROOF — it's on disk, not in the prompt"
echo "  \$ ls ./.demo-mem"; ls ./.demo-mem | sed 's/^/    /'; echo
echo "  \$ cat ./.demo-mem/prefs.json   (units=IMPERIAL — the correction overwrote metric)"; echo
cat ./.demo-mem/prefs.json | sed 's/^/    /'; echo
echo "  \$ facts stored: $(wc -l < ./.demo-mem/facts.jsonl)"
pause 4

banner "BEAT 2 — Cross-session recall  (brand-new process, nothing replayed)"
printf '%s\n' \
"What am I allergic to, and what units should you use with me?" \
"What's my daughter's name and what am I building?" \
> /tmp/recall.txt
python -m memoryagent.cli < /tmp/recall.txt 2>&1 | grep -E "loaded:|you>|aegis>" | sed 's/^/  /'
pause 4

banner "BEAT 3 — Bounded recall  (memory grows forever; the prompt can't)"
echo "  Starting the FastAPI service...";
uvicorn memoryagent.app:app --port 8000 --log-level warning &
UV=$!; sleep 6
echo "  Piling on 40 extra memories for user 'sam'..."
for i in $(seq 1 40); do
  curl -s localhost:8000/chat -H 'content-type: application/json' \
    -d "{\"user\":\"sam\",\"text\":\"For the record, fact number $i is XYZ-$i.\"}" >/dev/null
done
echo; echo "  \$ stats  (everything is stored):"
curl -s localhost:8000/memory/sam/stats | sed 's/^/    /'; echo
echo "  \$ recall under a TIGHT budget (400 tok, top_k 5) — only the salient few come back:"
curl -s "localhost:8000/memory/sam/recall?q=what+am+I+allergic+to&budget=400&top_k=5" | sed 's/^/    /'; echo
pause 5

banner "BEAT 4 — Forgetting  (low-value episodes decay & prune; facts survive)"
echo "  \$ stats before forget:"; curl -s localhost:8000/memory/sam/stats | sed 's/^/    /'; echo
echo "  \$ POST /memory/sam/forget:"; curl -s -X POST localhost:8000/memory/sam/forget | sed 's/^/    /'; echo
echo "  \$ stats after — episodes pruned, durable facts untouched:"; curl -s localhost:8000/memory/sam/stats | sed 's/^/    /'; echo
kill $UV 2>/dev/null
pause 4

banner "PROVEN, NOT VIBES — full suite, no Qwen key required (~1s)"
# Run the suite in a CLEAN env — the aggressive demo decay/floor vars must not leak in.
env -u DECAY_HALFLIFE_DAYS -u SALIENCE_FLOOR -u RECALL_TOKEN_BUDGET -u RECALL_TOP_K -u MEMORY_DIR \
    python -m pytest -q 2>&1 | tail -4 | sed 's/^/  /'
pause 3

banner "Cross-session recall · bounded budget · decay-based forgetting — on Qwen Cloud"
echo "  All original code · MIT · deployed on Alibaba Cloud"
pause 3
touch /tmp/demo_done
