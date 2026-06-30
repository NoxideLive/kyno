# Domain gateway runbook

Two-machine workflow: **train** on a GPU box with Groq access, **deploy and verify** on your dev machine.

## Overview

| Step | Training machine | Dev machine (this repo) |
|------|------------------|-------------------------|
| Pull code | `git pull` | `git pull` after training machine pushes |
| Generate data | Groq coupled pipeline | — |
| Train Phi LoRA | `train_phi.py` (CUDA) | — |
| Eval + threshold | `eval_domain_classifier.py` | Re-run eval against live gateway |
| Commit | Adapter + `training/domain/*.jsonl` | — |
| Run gateway | Optional smoke test | `uvicorn` + Convex env |

Blocking rule (gateway and Convex):

- Block when `label === off_topic`, **or**
- Block when `label === on_topic` **and** `confidence < DOMAIN_CONFIDENCE_THRESHOLD`

When `DOMAIN_GATEWAY_ENABLED=true` and the gateway is unreachable, Convex **fail-closed** (message is not sent to Groq).

---

## Training machine

Requirements:

- NVIDIA GPU with **8 GB+ VRAM** (Phi QLoRA)
- Python 3.11+
- `GROQ_API_KEY` with access to `openai/gpt-oss-120b` and `openai/gpt-oss-20b`
- Repo cloned at the same path you use locally (e.g. `/code/riv/kyno`)

### 1. Environment

```bash
cd /code/riv/kyno

python3 -m venv --without-pip .venv
curl -sS https://bootstrap.pypa.io/get-pip.py | .venv/bin/python
source .venv/bin/activate

pip install -r scripts/requirements-data.txt
pip install -r services/phi-gateway/requirements.txt
pip install -r services/phi-gateway/requirements-phi.txt
```

Set Groq key (env or `.env.local`):

```bash
export GROQ_API_KEY=gsk_...
```

Optional: copy tuning from [`training/domain/pipeline.config.json`](../training/domain/pipeline.config.json) before a run. Defaults are checked in.

### 2. Syllabus inputs (once per grade refresh)

```bash
python3 scripts/pull_syllabus.py --all-grades --skip-existing
```

Dry-run the coupled pipeline to see chunk counts:

```bash
python3 scripts/build_domain_training_data.py --grade 6 --dry-run
```

### 3. Generate training data (Groq)

Full run (~all grades, parallel workers from config):

```bash
python3 scripts/build_domain_training_data.py --all-grades
```

Outputs:

- `training/domain/train.jsonl`, `val.jsonl`, `test.jsonl`, `data.jsonl`
- `training/domain/generation_report.json` — inspect drops and extract failures
- `data/syllabus/grade-N/mathematics/topics.json` — per-chunk extracts

Curated edge cases in [`training/domain/curated.jsonl`](../training/domain/curated.jsonl) are **always pinned to train**. Do not add regression rows to train/val/test — [`training/domain/regression.jsonl`](../training/domain/regression.jsonl) is eval-only.

Check balance after generation:

```bash
python3 - <<'PY'
import json
from pathlib import Path
rows = [json.loads(l) for l in Path("training/domain/data.jsonl").read_text().splitlines() if l.strip()]
on = sum(1 for r in rows if r["label"] == "on_topic")
off = len(rows) - on
print(f"total={len(rows)} on_topic={on} ({100*on/len(rows):.1f}%) off_topic={off}")
PY
```

Target **~45–55%** off_topic after dedupe (tune via `pipeline.config.json` if needed).

### 4. Train Phi LoRA

```bash
python services/phi-gateway/train_phi.py
# multi-GPU:
# accelerate launch services/phi-gateway/train_phi.py
```

Adapter written to `services/phi-gateway/models/phi-domain-lora/`.

Val loss is logged each epoch when `val.jsonl` is non-empty.

### 5. Evaluate and pick threshold

```bash
python3 scripts/eval_domain_classifier.py
```

Read `training/domain/eval_report.json` → `recommended_threshold`.

Regression set must pass (0 failures in report):

| Input | Expected |
|-------|----------|
| `fractions`, `what about fractions` | allow |
| `Caps`, `all caps`, `write in caps` | block |
| `peanuts in CAPS`, `Grade 11 Mathematical Literacy` | block |
| `Grade 6 fractions`, `What is CAPS?` | allow |

Note the recommended threshold — you will set it on the dev machine.

### 6. Smoke test gateway locally

```bash
cd services/phi-gateway
export DOMAIN_CONFIDENCE_THRESHOLD=0.55   # replace with eval recommendation
uvicorn server:app --host 0.0.0.0 --port 8090
```

In another shell:

```bash
curl -s -X POST http://localhost:8090/classify/domain \
  -H 'Content-Type: application/json' \
  -d '{"text":"fractions"}' | jq .

curl -s -X POST http://localhost:8090/classify/domain \
  -H 'Content-Type: application/json' \
  -d '{"text":"Caps"}' | jq .
```

Expect `fractions` → `blocked: false`, `Caps` → `blocked: true`.

### 7. Commit and push

```bash
git add training/domain/*.jsonl training/domain/pipeline.config.json training/domain/eval.config.json
git add services/phi-gateway/models/phi-domain-lora/
git add data/syllabus/   # if topics.json / ATP text changed during extract
git commit -m "$(cat <<'EOF'
Retrain domain gate LoRA on coupled syllabus pipeline.

Regenerate train/val/test splits, update adapter weights, and record eval threshold.
EOF
)"
git push
```

Include `training/domain/eval_report.json` if you want the threshold choice recorded in git.

---

## Dev machine (after pull)

### 1. Gateway

```bash
cd /code/riv/kyno
source .venv/bin/activate   # same phi deps as training machine
pip install -r services/phi-gateway/requirements-phi.txt

cd services/phi-gateway
export DOMAIN_CONFIDENCE_THRESHOLD=0.55   # from eval_report.json on training machine
uvicorn server:app --host 0.0.0.0 --port 8090
```

If the gateway runs on another host, use that URL in Convex instead of `localhost`.

### 2. Convex env

```bash
npx convex env set PHI_GATEWAY_URL http://localhost:8090
npx convex env set DOMAIN_GATEWAY_ENABLED true
npx convex env set DOMAIN_CONFIDENCE_THRESHOLD 0.55
```

Replace `0.55` with the value from `training/domain/eval_report.json`.

### 3. Verify

```bash
python3 scripts/eval_domain_classifier.py --gateway-url http://localhost:8090
```

Then send test messages in the app: `fractions` (allow), `Caps` (block).

---

## Config reference

All pipeline tuning: [`training/domain/pipeline.config.json`](../training/domain/pipeline.config.json)

Eval sweep range: [`training/domain/eval.config.json`](../training/domain/eval.config.json)

| CLI | Purpose |
|-----|---------|
| `build_domain_training_data.py --all-grades` | Full Groq generate |
| `build_domain_training_data.py --grade N --dry-run` | Chunk count only |
| `generate_domain_training_data.py --total 800` | Template fallback (no Groq) |
| `eval_domain_classifier.py` | Local classifier + threshold sweep |
| `eval_domain_classifier.py --gateway-url URL` | HTTP gateway eval |

Template fallback is for quick iteration without Groq; production retrain should use the coupled pipeline.
