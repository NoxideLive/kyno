"""Phi-4-mini-instruct configuration aligned with Microsoft's sample_finetune.py.

Reference: https://huggingface.co/microsoft/Phi-4-mini-instruct/blob/main/sample_finetune.py
"""

from __future__ import annotations

from pathlib import Path

PHI_MODEL_ID = "microsoft/Phi-4-mini-instruct"
MODEL_DIR = Path(__file__).resolve().parent / "models"
PHI_ADAPTER_DIR = MODEL_DIR / "phi-domain-lora"

DOMAIN_SYSTEM_PROMPT = (
    "You classify whether a user message is about South African CAPS Mathematics "
    "(Grades 1–12): syllabus, ATP/teaching plans, assessments, and study help. "
    "Reply with exactly one token: on_topic or off_topic."
)

# Microsoft sample_finetune.py defaults
LORA_CONFIG = {
    "r": 4,
    "lora_alpha": 8,
    "lora_dropout": 0.05,
    "bias": "none",
    "task_type": "CAUSAL_LM",
    "target_modules": ["qkv_proj", "o_proj"],
    "modules_to_save": None,
}

TRAINING_CONFIG = {
    "bf16": True,
    "learning_rate": 2e-4,
    "logging_steps": 20,
    "lr_scheduler_type": "cosine",
    "num_train_epochs": 3,
    "per_device_train_batch_size": 1,
    "gradient_accumulation_steps": 4,
    "gradient_checkpointing": True,
    "gradient_checkpointing_kwargs": {"use_reentrant": False},
    "warmup_ratio": 0.1,
    "save_total_limit": 1,
    "max_seq_length": 256,
}
