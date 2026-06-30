# CAPS Mathematics domain gateway (Phi-4-mini-instruct)

Self-hosted FastAPI service that classifies chat messages as on-topic (CAPS Maths Gr 1–12) or off-topic before the main LLM.

**Full two-machine workflow:** [`docs/domain-gateway-runbook.md`](../../docs/domain-gateway-runbook.md)

## Quick reference

### Training machine (GPU + Groq)

```bash
export GROQ_API_KEY=gsk_...
python3 scripts/build_domain_training_data.py --all-grades
python services/phi-gateway/train_phi.py
python3 scripts/eval_domain_classifier.py
# commit adapter + training/domain/*.jsonl, push
```

### Dev machine (after pull)

```bash
export DOMAIN_CONFIDENCE_THRESHOLD=<from eval_report.json>
uvicorn server:app --host 0.0.0.0 --port 8090   # in services/phi-gateway

npx convex env set PHI_GATEWAY_URL http://localhost:8090
npx convex env set DOMAIN_GATEWAY_ENABLED true
npx convex env set DOMAIN_CONFIDENCE_THRESHOLD <same value>

python3 scripts/eval_domain_classifier.py --gateway-url http://localhost:8090
```

## Python environment

```bash
cd /code/riv/kyno
python3 -m venv --without-pip .venv
curl -sS https://bootstrap.pypa.io/get-pip.py | .venv/bin/python
source .venv/bin/activate

pip install -r scripts/requirements-data.txt          # data pipeline
pip install -r services/phi-gateway/requirements.txt
pip install -r services/phi-gateway/requirements-phi.txt   # train + Phi inference
```

## Training data

Tuning lives in [`training/domain/pipeline.config.json`](../../training/domain/pipeline.config.json).

| CLI flag | Purpose |
|----------|---------|
| `--grade N` / `--all-grades` | Scope |
| `--config PATH` | Config file (default: `training/domain/pipeline.config.json`) |
| `--dry-run` | Count chunks, no Groq calls |

Coupled pipeline (recommended): LLM extract → CAPS context → LLM generate → dedupe → splits. Curated rows pinned to train. No regex extract fallback.

Template fallback (no Groq): `python3 scripts/generate_domain_training_data.py --total 800`

Regression eval only: [`training/domain/regression.jsonl`](../../training/domain/regression.jsonl)

## Runtime

Backend priority: **Phi LoRA + hybrid overrides → sklearn → token log-odds → keywords**.

Blocking: `off_topic`, or `on_topic` with confidence below `DOMAIN_CONFIDENCE_THRESHOLD`.

Convex fail-closed when gateway enabled but unreachable.

## API

```
POST /classify/domain
{ "text": "What does Grade 6 CAPS cover for fractions?" }
→ { "label": "on_topic", "confidence": 0.92, "backend": "phi-lora+hybrid", "blocked": false }
```

## Phi model

- Base: `microsoft/Phi-4-mini-instruct`
- LoRA: r=16, alpha=32, dropout=0.05, `target_modules="all-linear"`
- Adapter: `services/phi-gateway/models/phi-domain-lora/`
