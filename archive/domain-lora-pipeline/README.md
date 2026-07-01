# Archived: LoRA / Groq domain training pipeline

Moved here during prompt-only domain gateway cleanup. Not used by production.

## What replaced it

- **Classification:** bare Phi-4-mini-instruct + rich system prompt (`services/phi-gateway/`)
- **Topic data:** `POST /pipeline/rebuild` on phi-gateway (Phi JSON extract from CAPS PDFs)
- **Manual:** PDF download (`scripts/pull_syllabus.py --caps-only`), `data/domain/prompt_examples.json`, eval JSONL

## Contents

| Path | Was |
|------|-----|
| `scripts/build_domain_training_data.py` | Groq coupled ATP → training JSONL |
| `scripts/caps_chunker_regex.py` | Regex CAPS PDF extraction |
| `services/phi-gateway/train_phi.py` | QLoRA fine-tune |
| `training/domain/*.jsonl` | LoRA train/val/test splits |
| `docs/research/` | Pre-Phi gateway design notes |

Restore from here only if retraining LoRA or reviving the Groq data pipeline.
