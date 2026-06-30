# CAPS Mathematics domain gateway (Phi-4-mini-instruct)

Self-hosted FastAPI service that classifies chat messages as on-topic (CAPS Maths Gr 1–12) or off-topic before the main LLM.

Follows [Microsoft Phi-4-mini-instruct sample_finetune.py](https://huggingface.co/microsoft/Phi-4-mini-instruct/blob/main/sample_finetune.py).

## 1. Python environment (PEP 668 / Ubuntu)

Do not install packages into system Python. Use a project venv:

```bash
cd /code/riv/kyno
python3 -m venv --without-pip .venv
curl -sS https://bootstrap.pypa.io/get-pip.py | .venv/bin/python
source .venv/bin/activate
```

## 2. Install dependencies

**API + CPU fallback classifier:**

```bash
pip install -r services/phi-gateway/requirements.txt
```

**Phi fine-tuning / GPU inference (optional):**

```bash
pip install -r services/phi-gateway/requirements-phi.txt
```

Microsoft recommends for Phi training:

```bash
pip install accelerate bitsandbytes peft==0.14.0 "transformers>=4.48.1" trl datasets
```

## 3. Prepare training data

```bash
# Pull DBE CAPS/ATP PDFs (grades 1–12)
python3 scripts/pull_syllabus.py --all-grades --skip-existing

# Extract ATP topics
python3 scripts/extract_atp_topics.py --all-grades

# Generate labeled jsonl
python3 scripts/generate_domain_training_data.py
```

## 4. Train

**Phi QLoRA (primary — requires CUDA GPU):**

```bash
python services/phi-gateway/train_phi.py
# or multi-GPU:
accelerate launch services/phi-gateway/train_phi.py
```

Adapter saved to `services/phi-gateway/models/phi-domain-lora/`.

**CPU fallback (no GPU):**

```bash
python services/phi-gateway/train_simple.py
# or with sklearn when available:
python services/phi-gateway/train.py
```

## 5. Run server

```bash
cd services/phi-gateway
uvicorn server:app --host 0.0.0.0 --port 8090
```

Backend priority at runtime: **Phi LoRA → sklearn → token log-odds → keywords**.

## 6. Convex env

```bash
npx convex env set PHI_GATEWAY_URL http://localhost:8090
npx convex env set DOMAIN_GATEWAY_ENABLED true
```

## API

```
POST /classify/domain
{ "text": "What does Grade 6 CAPS cover for fractions?" }
→ { "label": "on_topic", "confidence": 0.92, "backend": "phi-lora", "blocked": false }
```

## Phi model

- Base: `microsoft/Phi-4-mini-instruct`
- LoRA: r=16, alpha=32, dropout=0.05, `target_modules="all-linear"` (Microsoft defaults)
- Task: SFT chat classification → assistant replies `on_topic` or `off_topic`
