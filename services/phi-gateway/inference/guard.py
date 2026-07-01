"""Generic HuggingFace guard model adapter."""

from __future__ import annotations

from dataclasses import dataclass

from gateway_config import AdapterKind, HfModelId
from inference.common import (
    clear_cuda_cache,
    inference_lock,
    load_4bit_enabled,
    log,
    model_device,
    raise_inference_error,
)


@dataclass
class GuardBundle:
    model_id: HfModelId
    adapter: AdapterKind
    model: object
    tokenizer: object
    device: str


def load_guard(model_id: HfModelId) -> GuardBundle:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA required for phi-gateway")

    model_kwargs: dict = {
        "trust_remote_code": True,
        "device_map": "cuda:0",
    }
    if load_4bit_enabled():
        model_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )
        model_kwargs["torch_dtype"] = torch.bfloat16
    else:
        model_kwargs["torch_dtype"] = torch.bfloat16

    log(f"Loading guard model ({model_id}), cuda=True")
    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(model_id, **model_kwargs)
    model.eval()

    device = model_device(model)
    if not device.startswith("cuda"):
        raise RuntimeError(f"model loaded on {device}, expected cuda:0")

    mem_gb = torch.cuda.memory_allocated(0) / (1024**3)
    log(f"Guard ready: {model_id} on {device} ({mem_gb:.2f} GiB VRAM)")

    return GuardBundle(
        model_id=model_id,
        adapter="guard",
        model=model,
        tokenizer=tokenizer,
        device=device,
    )


def unload_guard(bundle: GuardBundle) -> None:
    import gc

    import torch

    del bundle.model
    del bundle.tokenizer
    gc.collect()
    if torch.cuda.is_available():
        clear_cuda_cache()


def _guard_conversation(text: str) -> list[dict]:
    return [
        {
            "role": "user",
            "content": [{"type": "text", "text": text.strip()}],
        }
    ]


def _parse_guard_output(raw: str) -> tuple[str, float]:
    stripped = raw.strip().lower()
    first_line = stripped.splitlines()[0] if stripped else ""
    if first_line.startswith("unsafe"):
        return "jailbreak_attempted", 1.0
    if first_line.startswith("safe"):
        return "safe", 1.0
    if "unsafe" in stripped:
        return "jailbreak_attempted", 1.0
    return "safe", 1.0


def classify_jailbreak_with_guard(bundle: GuardBundle, text: str) -> dict:
    import torch

    trimmed = text.strip()
    if not trimmed:
        return {"label": "safe", "confidence": 1.0, "backend": bundle.model_id}

    conversation = _guard_conversation(trimmed)
    tokenizer = bundle.tokenizer
    model = bundle.model
    device = bundle.device

    lock = inference_lock()
    with lock:
        if device.startswith("cuda"):
            clear_cuda_cache()
        try:
            input_ids = tokenizer.apply_chat_template(
                conversation, return_tensors="pt"
            ).to(device)
            prompt_len = input_ids.shape[1]
            pad_token_id = getattr(tokenizer, "pad_token_id", None) or 0
            with torch.no_grad():
                output = model.generate(
                    input_ids,
                    max_new_tokens=20,
                    pad_token_id=pad_token_id,
                    do_sample=False,
                )
            generated = tokenizer.decode(
                output[0, prompt_len:], skip_special_tokens=True
            )
            if device.startswith("cuda"):
                clear_cuda_cache()
        except Exception as exc:  # noqa: BLE001
            raise_inference_error(exc, context="guard classification")

    label, confidence = _parse_guard_output(generated)
    return {
        "label": label,
        "confidence": confidence,
        "backend": bundle.model_id,
    }
