# CAPS Mathematics domain gateway (multi-model)

FastAPI service in Docker: **HuggingFace models on GPU** for jailbreak + domain classification and CAPS pipeline rebuild. Same HTTP API regardless of profile.

**Runbook:** [`docs/domain-gateway-runbook.md`](../../docs/domain-gateway-runbook.md)

## Model profiles

Set `PHI_GATEWAY_PROFILE` in `.env.local` (default `medium`). Per-role overrides use full HuggingFace `org/name` ids.

| Profile | Jailbreak | Domain | Pipeline |
|---------|-----------|--------|----------|
| `small` | `Qwen/Qwen2.5-1.5B-Instruct` | same | same |
| `medium` | `microsoft/Phi-4-mini-instruct` | same | same |
| `large` | `meta-llama/Llama-Guard-3-1B` | `microsoft/Phi-4-mini-instruct` | same |

```bash
PHI_GATEWAY_PROFILE=medium
# PHI_GATEWAY_PIPELINE_MODEL=microsoft/Phi-4-mini-instruct
# HF_TOKEN=...   # required for gated models (Llama Guard)
```

Classify models load at boot (one singleton per distinct HF id). Pipeline uses the same instance when the id matches; otherwise it **swaps** models for the duration of `/pipeline/rebuild`.

## Quick start

```bash
./scripts/dev-init.sh
```

Phi gateway only:

```bash
docker compose --env-file .env.local up --build -d phi-gateway
```

After editing Python under `services/phi-gateway/`:

```bash
docker compose --env-file .env.local up --build -d phi-gateway
```

## Host scripts (gateway must be running)

```bash
export PHI_GATEWAY_URL=http://localhost:8090
export PHI_GATEWAY_API_KEY=...   # from .env.local
python3 scripts/run_domain_pipeline.py
python3 scripts/eval_domain_classifier.py
python3 scripts/eval_jailbreak_classifier.py
```

## API

`backend` fields in classify responses are the HuggingFace `model_id` for that stage.

```
GET /health
→ { "profile": "medium", "roles": {...}, "models_loaded": [...], "phi_loaded": true, ... }

POST /classify/message
→ { "allowed": true, "jailbreak": { "backend": "microsoft/Phi-4-mini-instruct", ... }, ... }
```

LoRA training archived under `archive/domain-lora-pipeline/`.
