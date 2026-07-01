"""Generic HuggingFace causal LM decoder adapter."""

from __future__ import annotations

import math
from dataclasses import dataclass

from gateway_config import AdapterKind, HfModelId
from inference.common import (
    build_classify_messages,
    classify_max_length,
    clear_cuda_cache,
    inference_lock,
    load_4bit_enabled,
    log,
    model_device,
    prompt_max_length,
    raise_inference_error,
)


@dataclass
class DecoderBundle:
    model_id: HfModelId
    adapter: AdapterKind
    model: object
    tokenizer: object
    device: str


def load_decoder(model_id: HfModelId) -> DecoderBundle:
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

    log(f"Loading decoder model ({model_id}), cuda=True")
    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    tokenizer.model_max_length = prompt_max_length()
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.unk_token
    tokenizer.pad_token_id = tokenizer.convert_tokens_to_ids(tokenizer.pad_token)
    tokenizer.padding_side = "left"

    model = AutoModelForCausalLM.from_pretrained(model_id, **model_kwargs)
    model.eval()

    device = model_device(model)
    if not device.startswith("cuda"):
        raise RuntimeError(f"model loaded on {device}, expected cuda:0")

    mem_gb = torch.cuda.memory_allocated(0) / (1024**3)
    log(f"Decoder ready: {model_id} on {device} ({mem_gb:.2f} GiB VRAM)")

    return DecoderBundle(
        model_id=model_id,
        adapter="decoder",
        model=model,
        tokenizer=tokenizer,
        device=device,
    )


def unload_decoder(bundle: DecoderBundle) -> None:
    import gc

    import torch

    del bundle.model
    del bundle.tokenizer
    gc.collect()
    if torch.cuda.is_available():
        clear_cuda_cache()


def classify_with_decoder(
    bundle: DecoderBundle,
    text: str,
    *,
    system_prompt: str,
    label_names: tuple[str, ...],
    history: list | None = None,
) -> dict:
    import torch

    model = bundle.model
    tokenizer = bundle.tokenizer
    device = bundle.device
    messages = build_classify_messages(text, system_prompt=system_prompt, history=history)

    lock = inference_lock()
    with lock:
        maybe_clear_cuda_cache_for_classify()
        try:
            prompt = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            max_len = classify_max_length()
            inputs = tokenizer(
                prompt, return_tensors="pt", truncation=True, max_length=max_len
            )
            if device.startswith("cuda"):
                inputs = {k: v.to(device) for k, v in inputs.items()}

            label_tokens = {
                label: tokenizer.encode(label, add_special_tokens=False)
                for label in label_names
            }

            with torch.inference_mode():
                outputs = model(**inputs, use_cache=False)
                next_logits = outputs.logits[0, -1, :]
                scores = {
                    label: float(next_logits[token_ids[0]].item())
                    for label, token_ids in label_tokens.items()
                }
                del outputs

            maybe_clear_cuda_cache_for_classify()
        except Exception as exc:  # noqa: BLE001
            raise_inference_error(exc, context="classification")

    exp_scores = {label: math.exp(scores[label]) for label in label_names}
    total = sum(exp_scores.values())
    probs = {label: exp_scores[label] / total for label in label_names}
    best_label = max(probs, key=probs.get)
    return {
        "label": best_label,
        "confidence": probs[best_label],
        "backend": bundle.model_id,
    }


def generate_with_decoder(
    bundle: DecoderBundle,
    *,
    system: str,
    user: str,
    max_new_tokens: int = 1024,
    temperature: float = 0.1,
) -> str:
    import torch

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    model = bundle.model
    tokenizer = bundle.tokenizer
    device = bundle.device
    prompt = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    max_len = prompt_max_length()
    inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=max_len)
    if device.startswith("cuda"):
        inputs = {k: v.to(device) for k, v in inputs.items()}

    gen_kwargs: dict = {
        "max_new_tokens": max_new_tokens,
        "pad_token_id": tokenizer.pad_token_id,
    }
    if temperature > 0:
        gen_kwargs["do_sample"] = True
        gen_kwargs["temperature"] = temperature
    else:
        gen_kwargs["do_sample"] = False

    lock = inference_lock()
    with lock:
        if device.startswith("cuda"):
            clear_cuda_cache()
        try:
            with torch.no_grad():
                output_ids = model.generate(**inputs, **gen_kwargs)
        except Exception as exc:  # noqa: BLE001
            raise_inference_error(exc, context="generation")
        finally:
            if device.startswith("cuda"):
                clear_cuda_cache()

    new_tokens = output_ids[0, inputs["input_ids"].shape[1] :]
    return tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
