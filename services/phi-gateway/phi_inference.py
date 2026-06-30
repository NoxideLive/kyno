"""Load Phi-4-mini-instruct + domain LoRA adapter for classification inference."""

from __future__ import annotations

import math
import os
from functools import lru_cache

from phi_config import DOMAIN_SYSTEM_PROMPT, PHI_ADAPTER_DIR, PHI_MODEL_ID

_phi_unavailable_reason: str | None = None


def phi_available() -> bool:
    return _load_phi_classifier() is not None


def phi_unavailable_reason() -> str | None:
    _load_phi_classifier()
    return _phi_unavailable_reason


@lru_cache(maxsize=1)
def _load_phi_classifier():
    global _phi_unavailable_reason

    if not PHI_ADAPTER_DIR.is_dir():
        _phi_unavailable_reason = "adapter missing"
        return None

    try:
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    except ImportError:
        _phi_unavailable_reason = "install torch, transformers, peft, bitsandbytes"
        return None

    use_cuda = torch.cuda.is_available()
    load_4bit = os.environ.get("PHI_LOAD_4BIT", "true").lower() in ("1", "true", "yes")

    model_kwargs: dict = {
        "trust_remote_code": True,
        "device_map": "auto" if use_cuda else None,
    }

    if use_cuda and load_4bit:
        model_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )
        model_kwargs["torch_dtype"] = torch.bfloat16
    elif use_cuda:
        model_kwargs["torch_dtype"] = torch.bfloat16
    else:
        model_kwargs["torch_dtype"] = torch.float32

    try:
        tokenizer = AutoTokenizer.from_pretrained(PHI_MODEL_ID, trust_remote_code=True)
        tokenizer.model_max_length = 512
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.unk_token
        tokenizer.pad_token_id = tokenizer.convert_tokens_to_ids(tokenizer.pad_token)
        tokenizer.padding_side = "left"

        base = AutoModelForCausalLM.from_pretrained(PHI_MODEL_ID, **model_kwargs)
        model = PeftModel.from_pretrained(base, str(PHI_ADAPTER_DIR))
        model.eval()

        return {"model": model, "tokenizer": tokenizer, "device": "cuda" if use_cuda else "cpu"}
    except Exception as exc:  # noqa: BLE001
        _phi_unavailable_reason = str(exc)
        return None


def classify_with_phi(text: str) -> dict | None:
    bundle = _load_phi_classifier()
    if bundle is None:
        return None

    import torch

    model = bundle["model"]
    tokenizer = bundle["tokenizer"]

    messages = [
        {"role": "system", "content": DOMAIN_SYSTEM_PROMPT},
        {"role": "user", "content": text.strip()},
    ]
    prompt = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs = tokenizer(prompt, return_tensors="pt")
    if bundle["device"] == "cuda":
        inputs = {k: v.to(model.device) for k, v in inputs.items()}

    label_tokens = {
        "on_topic": tokenizer.encode("on_topic", add_special_tokens=False),
        "off_topic": tokenizer.encode("off_topic", add_special_tokens=False),
    }

    with torch.no_grad():
        outputs = model(**inputs)
        next_logits = outputs.logits[0, -1, :]

        scores: dict[str, float] = {}
        for label, token_ids in label_tokens.items():
            scores[label] = float(next_logits[token_ids].mean().item())

        if scores["on_topic"] >= scores["off_topic"]:
            # Softmax over two scores for a confidence proxy
            a, b = scores["on_topic"], scores["off_topic"]
            exp_a, exp_b = math.exp(a), math.exp(b)
            confidence = exp_a / (exp_a + exp_b)
            return {"label": "on_topic", "confidence": confidence, "backend": "phi-lora"}

        exp_a, exp_b = math.exp(scores["on_topic"]), math.exp(scores["off_topic"])
        confidence = exp_b / (exp_a + exp_b)
        return {"label": "off_topic", "confidence": confidence, "backend": "phi-lora"}
