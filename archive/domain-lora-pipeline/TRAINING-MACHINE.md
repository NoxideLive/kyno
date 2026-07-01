# Training machine — domain gate retrain

Pull latest `main`, then run this sequence. Full details: [`docs/domain-gateway-runbook.md`](docs/domain-gateway-runbook.md).

```bash
cd /code/riv/kyno
git pull origin main

python3 -m venv --without-pip .venv
curl -sS https://bootstrap.pypa.io/get-pip.py | .venv/bin/python
source .venv/bin/activate

pip install -r scripts/requirements-data.txt
pip install -r services/phi-gateway/requirements.txt
pip install -r services/phi-gateway/requirements-phi.txt

export GROQ_API_KEY=gsk_...   # or .env.local

python3 scripts/build_domain_training_data.py --grade 6 --dry-run   # optional sanity check
python3 scripts/build_domain_training_data.py --all-grades

python services/phi-gateway/train_phi.py
python3 scripts/eval_domain_classifier.py
```

Note `recommended_threshold` from `training/domain/eval_report.json`. Regression failures should be **0**.

Smoke test:

```bash
cd services/phi-gateway
export DOMAIN_CONFIDENCE_THRESHOLD=<from eval_report>
uvicorn server:app --host 0.0.0.0 --port 8090
```

```bash
curl -s -X POST http://localhost:8090/classify/domain -H 'Content-Type: application/json' -d '{"text":"fractions"}'
curl -s -X POST http://localhost:8090/classify/domain -H 'Content-Type: application/json' -d '{"text":"Caps"}'
```

Commit and push when done:

```bash
cd /code/riv/kyno
git add training/domain/*.jsonl training/domain/eval_report.json services/phi-gateway/models/phi-domain-lora/
git commit -m "Retrain domain gate LoRA on coupled syllabus pipeline."
git push origin main
```

**Send back:** `recommended_threshold` and confirm regression set passes.

Dev machine after pull: start gateway with that threshold, set Convex env (`PHI_GATEWAY_URL`, `DOMAIN_GATEWAY_ENABLED`, `DOMAIN_CONFIDENCE_THRESHOLD`), run `python3 scripts/eval_domain_classifier.py --gateway-url http://localhost:8090`.
