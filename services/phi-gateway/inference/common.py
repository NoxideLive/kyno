"""Shared inference types and GPU helpers."""

from __future__ import annotations

import os
import sys
import threading
from typing import Literal, TypedDict

_inference_lock = threading.Lock()

HistoryRole = Literal["user", "assistant"]


class HistoryTurn(TypedDict):
    role: HistoryRole
    content: str


class StageClassification(TypedDict):
    label: str
    confidence: float
    backend: str


class CompiledClassification(TypedDict):
    allowed: bool
    blocked: bool
    block_reason: Literal["jailbreak_attempted", "off_topic"] | None
    jailbreak: StageClassification
    domain: StageClassification
    backend: str


class GatewayInferenceError(RuntimeError):
    """Transient or resource failure during model forward pass."""


CLASSIFY_UNAVAILABLE = "Classify models temporarily unloaded for pipeline"


CLASSIFY_HISTORY_MAX_TURNS = 6
CLASSIFY_TURN_MAX_CHARS = 300
_SMALL_GPU_VRAM_GIB = 4.0


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def inference_lock() -> threading.Lock:
    return _inference_lock


def clear_cuda_cache(*, sync: bool = True) -> None:
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            if sync:
                torch.cuda.synchronize()
    except Exception:  # noqa: BLE001
        return


def classify_clear_cuda_cache_enabled() -> bool:
    """Whether to empty/sync CUDA cache around each classify forward pass."""
    raw = os.environ.get("PHI_CLASSIFY_CLEAR_CUDA_CACHE", "false").strip().lower()
    return raw in ("1", "true", "yes", "on")


def maybe_clear_cuda_cache_for_classify() -> None:
    if classify_clear_cuda_cache_enabled():
        clear_cuda_cache()


def is_cuda_oom(exc: BaseException) -> bool:
    try:
        import torch
    except ImportError:
        return False
    if isinstance(exc, torch.cuda.OutOfMemoryError):
        return True
    message = str(exc).lower()
    return "out of memory" in message or "cuda out of memory" in message


def raise_inference_error(exc: BaseException, *, context: str) -> None:
    if is_cuda_oom(exc):
        clear_cuda_cache()
        log(f"CUDA OOM during {context}: {exc}")
        raise GatewayInferenceError(
            "CUDA out of memory during classification; retry shortly"
        ) from exc
    raise exc


def prompt_max_length() -> int:
    raw = os.environ.get("PHI_MAX_SEQ_LENGTH", "8192")
    try:
        return int(raw)
    except ValueError:
        return 8192


def classify_max_length() -> int:
    raw = os.environ.get("PHI_CLASSIFY_MAX_SEQ_LENGTH", "1024")
    try:
        return int(raw)
    except ValueError:
        return 1024


def load_4bit_enabled() -> bool:
    return os.environ.get("PHI_LOAD_4BIT", "true").lower() in ("1", "true", "yes")


def trim_history_for_classify(history: list[HistoryTurn] | None) -> list[HistoryTurn]:
    if not history:
        return []
    recent = history[-CLASSIFY_HISTORY_MAX_TURNS:]
    trimmed: list[HistoryTurn] = []
    for turn in recent:
        role = turn["role"]
        if role not in ("user", "assistant"):
            continue
        content = turn["content"].strip()[:CLASSIFY_TURN_MAX_CHARS]
        if content:
            trimmed.append({"role": role, "content": content})
    return trimmed


def build_classify_messages(
    text: str,
    *,
    system_prompt: str,
    history: list[HistoryTurn] | None,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for turn in trim_history_for_classify(history):
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": text.strip()[:CLASSIFY_TURN_MAX_CHARS]})
    return messages


def compile_classification(
    jailbreak: StageClassification,
    domain: StageClassification,
) -> CompiledClassification:
    backend = jailbreak["backend"]
    if jailbreak["label"] == "jailbreak_attempted":
        return {
            "allowed": False,
            "blocked": True,
            "block_reason": "jailbreak_attempted",
            "jailbreak": jailbreak,
            "domain": domain,
            "backend": backend,
        }
    if domain["label"] == "off_topic":
        return {
            "allowed": False,
            "blocked": True,
            "block_reason": "off_topic",
            "jailbreak": jailbreak,
            "domain": domain,
            "backend": backend,
        }
    return {
        "allowed": True,
        "blocked": False,
        "block_reason": None,
        "jailbreak": jailbreak,
        "domain": domain,
        "backend": backend,
    }


def model_device(model) -> str:
    try:
        return str(next(model.parameters()).device)
    except StopIteration:
        return "cpu"
