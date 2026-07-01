"""Public inference facade for phi-gateway (multi-model)."""

from __future__ import annotations

from inference.common import (
    CompiledClassification,
    GatewayInferenceError,
    HistoryTurn,
    StageClassification,
    compile_classification,
)
from inference.registry import (
    boot_complete,
    boot_gateway,
    gateway_available,
    gateway_backend_name,
    gateway_unavailable_reason,
    get_router,
    gpu_device_info,
    health_models_loaded,
    health_roles,
    pipeline_session,
)

# Backward-compatible aliases
PhiInferenceError = GatewayInferenceError
boot_phi = boot_gateway
phi_available = gateway_available
phi_unavailable_reason = gateway_unavailable_reason
phi_backend_name = gateway_backend_name


def classify_jailbreak_with_phi(text: str) -> dict | None:
    if not gateway_available():
        return None
    try:
        return get_router().classify_jailbreak(text)
    except GatewayInferenceError:
        raise
    except RuntimeError:
        return None


def classify_domain_with_phi(
    text: str,
    history: list[HistoryTurn] | None = None,
) -> dict | None:
    if not gateway_available():
        return None
    try:
        return get_router().classify_domain(text, history=history)
    except GatewayInferenceError:
        raise
    except RuntimeError:
        return None


def classify_message_parallel(
    text: str,
    history: list[HistoryTurn] | None = None,
) -> CompiledClassification | None:
    if not gateway_available():
        return None
    try:
        return get_router().classify_message(text, history=history)
    except GatewayInferenceError:
        raise
    except RuntimeError:
        return None


def generate_text(
    *,
    system: str,
    user: str,
    max_new_tokens: int = 1024,
    temperature: float = 0.1,
) -> str:
    return get_router().generate_text(
        system=system,
        user=user,
        max_new_tokens=max_new_tokens,
        temperature=temperature,
    )


__all__ = [
    "CompiledClassification",
    "GatewayInferenceError",
    "HistoryTurn",
    "PhiInferenceError",
    "StageClassification",
    "boot_complete",
    "boot_gateway",
    "boot_phi",
    "classify_domain_with_phi",
    "classify_jailbreak_with_phi",
    "classify_message_parallel",
    "gateway_available",
    "gateway_backend_name",
    "gateway_unavailable_reason",
    "generate_text",
    "get_router",
    "gpu_device_info",
    "health_models_loaded",
    "health_roles",
    "phi_available",
    "phi_backend_name",
    "phi_unavailable_reason",
    "pipeline_session",
]
