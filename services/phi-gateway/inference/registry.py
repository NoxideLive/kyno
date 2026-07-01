"""Model registry, role router, and pipeline swap lifecycle."""

from __future__ import annotations

import gc
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Literal

from domain_prompt import build_domain_system_prompt
from gateway_config import (
    AdapterKind,
    GatewayRole,
    GatewayRoleConfig,
    HfModelId,
    PromptVariant,
    resolve_adapter,
    resolve_classify_prompt_variant,
    resolve_gateway_config,
)
from inference.common import (
    CLASSIFY_UNAVAILABLE,
    GatewayInferenceError,
    HistoryTurn,
    StageClassification,
    _SMALL_GPU_VRAM_GIB,
    clear_cuda_cache,
    compile_classification,
    log,
)
from inference.decoder import (
    DecoderBundle,
    classify_with_decoder,
    generate_with_decoder,
    load_decoder,
    unload_decoder,
)
from inference.guard import GuardBundle, classify_jailbreak_with_guard, load_guard, unload_guard
from jailbreak_prompt import build_jailbreak_system_prompt

Bundle = DecoderBundle | GuardBundle


@dataclass
class LoadedModelInfo:
    model_id: HfModelId
    adapter: AdapterKind


_registry: ModelRegistry | None = None
_vram_warning: str | None = None
_boot_failed_reason: str | None = None
_boot_complete = False
_classify_unavailable = False


class ModelRegistry:
    def __init__(self, config: GatewayRoleConfig) -> None:
        self._config = config
        self._bundles: dict[HfModelId, Bundle] = {}
        self._load_lock = threading.Lock()
        self._lifecycle_lock = threading.RLock()

    @property
    def config(self) -> GatewayRoleConfig:
        return self._config

    def is_loaded(self, model_id: HfModelId) -> bool:
        return model_id in self._bundles

    def list_loaded(self) -> list[LoadedModelInfo]:
        return [
            LoadedModelInfo(model_id=model_id, adapter=bundle.adapter)
            for model_id, bundle in sorted(self._bundles.items())
        ]

    def ensure_loaded(self, model_id: HfModelId) -> Bundle:
        existing = self._bundles.get(model_id)
        if existing is not None:
            return existing

        with self._load_lock:
            existing = self._bundles.get(model_id)
            if existing is not None:
                return existing

            adapter = resolve_adapter(model_id)

            if adapter == "guard":
                bundle: Bundle = load_guard(model_id)
            else:
                bundle = load_decoder(model_id)

            self._bundles[model_id] = bundle
            self._maybe_warn_vram()
            return bundle

    def unload(self, model_id: HfModelId) -> None:
        bundle = self._bundles.pop(model_id, None)
        if bundle is None:
            return
        if bundle.adapter == "guard":
            unload_guard(bundle)  # type: ignore[arg-type]
        else:
            unload_decoder(bundle)  # type: ignore[arg-type]
        gc.collect()
        clear_cuda_cache()

    def evict_all(self, *, except_ids: frozenset[HfModelId]) -> list[HfModelId]:
        evicted: list[HfModelId] = []
        for model_id in list(self._bundles.keys()):
            if model_id in except_ids:
                continue
            evicted.append(model_id)
            self.unload(model_id)
        return evicted

    def boot_classify_models(self) -> None:
        for model_id in sorted(self._config.classify_model_ids()):
            self.ensure_loaded(model_id)

    def _maybe_warn_vram(self) -> None:
        global _vram_warning
        try:
            import torch

            if not torch.cuda.is_available():
                return
            total_vram_gib = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            if total_vram_gib < _SMALL_GPU_VRAM_GIB and _vram_warning is None:
                _vram_warning = (
                    f"GPU has {total_vram_gib:.1f} GiB VRAM (< {_SMALL_GPU_VRAM_GIB:g} GiB); "
                    "classify may return 503 under load — keep PHI_CLASSIFY_CONCURRENCY=1"
                )
                log(f"WARNING: {_vram_warning}")
        except Exception:  # noqa: BLE001
            return

    def bundle_for_role(self, role: GatewayRole) -> Bundle:
        model_id = self._config.model_for(role)
        return self.ensure_loaded(model_id)


class RoleRouter:
    def __init__(self, registry: ModelRegistry) -> None:
        self._registry = registry

    @property
    def config(self) -> GatewayRoleConfig:
        return self._registry.config

    @property
    def prompt_variant(self) -> PromptVariant:
        return resolve_classify_prompt_variant(self.config.profile)

    def classify_available(self) -> bool:
        if _classify_unavailable:
            return False
        for model_id in self.config.classify_model_ids():
            if not self._registry.is_loaded(model_id):
                return False
        return True

    def unavailable_reason(self) -> str | None:
        if _boot_failed_reason:
            return _boot_failed_reason
        if _classify_unavailable:
            return CLASSIFY_UNAVAILABLE
        for model_id in self.config.classify_model_ids():
            if not self._registry.is_loaded(model_id):
                return f"Model not loaded: {model_id}"
        return None

    def classify_jailbreak(self, text: str) -> dict:
        self._require_classify_ready()
        spec = self.config.jailbreak
        bundle = self._registry.ensure_loaded(spec.model_id)
        if spec.adapter == "guard":
            return classify_jailbreak_with_guard(bundle, text)  # type: ignore[arg-type]
        return classify_with_decoder(
            bundle,  # type: ignore[arg-type]
            text,
            system_prompt=build_jailbreak_system_prompt(self.prompt_variant),
            label_names=("safe", "jailbreak_attempted"),
            history=[],
        )

    def classify_domain(self, text: str, history: list[HistoryTurn] | None = None) -> dict:
        self._require_classify_ready()
        spec = self.config.domain
        bundle = self._registry.ensure_loaded(spec.model_id)
        return classify_with_decoder(
            bundle,  # type: ignore[arg-type]
            text,
            system_prompt=build_domain_system_prompt(self.prompt_variant),
            label_names=("on_topic", "off_topic"),
            history=history,
        )

    def classify_message(
        self, text: str, history: list[HistoryTurn] | None = None
    ) -> dict:
        trimmed = text.strip()
        jailbreak_model = self.config.jailbreak.model_id
        domain_model = self.config.domain.model_id
        if not trimmed:
            return compile_classification(
                {
                    "label": "safe",
                    "confidence": 1.0,
                    "backend": jailbreak_model,
                },
                {
                    "label": "off_topic",
                    "confidence": 1.0,
                    "backend": domain_model,
                },
            )

        jailbreak_result = self.classify_jailbreak(trimmed)
        if jailbreak_model != domain_model:
            clear_cuda_cache()
        domain_result = self.classify_domain(trimmed, history)
        return compile_classification(
            {
                "label": str(jailbreak_result["label"]),
                "confidence": float(jailbreak_result["confidence"]),
                "backend": str(jailbreak_result["backend"]),
            },
            {
                "label": str(domain_result["label"]),
                "confidence": float(domain_result["confidence"]),
                "backend": str(domain_result["backend"]),
            },
        )

    def generate_text(
        self,
        *,
        system: str,
        user: str,
        max_new_tokens: int = 1024,
        temperature: float = 0.1,
    ) -> str:
        bundle = self._registry.bundle_for_role("pipeline")
        if bundle.adapter != "decoder":
            raise RuntimeError("Pipeline role requires a decoder model")
        return generate_with_decoder(
            bundle,  # type: ignore[arg-type]
            system=system,
            user=user,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
        )

    def _require_classify_ready(self) -> None:
        reason = self.unavailable_reason()
        if reason:
            raise GatewayInferenceError(reason)


def get_registry() -> ModelRegistry:
    if _registry is None:
        raise RuntimeError("Gateway not booted")
    return _registry


def get_router() -> RoleRouter:
    return RoleRouter(get_registry())


def boot_gateway() -> None:
    global _registry, _boot_complete, _boot_failed_reason, _classify_unavailable
    try:
        config = resolve_gateway_config()
        registry = ModelRegistry(config)
        registry.boot_classify_models()
        _registry = registry
        _boot_complete = True
        _boot_failed_reason = None
        _classify_unavailable = False
    except Exception as exc:  # noqa: BLE001
        _boot_complete = False
        _boot_failed_reason = str(exc)
        log(f"Gateway boot failed: {exc}")
        raise


def boot_complete() -> bool:
    return _boot_complete and _registry is not None


def gateway_available() -> bool:
    if not boot_complete():
        return False
    try:
        return get_router().classify_available()
    except RuntimeError:
        return False


def gateway_unavailable_reason() -> str | None:
    if _boot_failed_reason:
        return _boot_failed_reason
    if not boot_complete():
        return "Gateway not booted"
    try:
        return get_router().unavailable_reason()
    except RuntimeError as exc:
        return str(exc)


def gateway_backend_name() -> str:
    if not boot_complete():
        return "gateway-unavailable"
    return get_registry().config.jailbreak.model_id


def gpu_device_info() -> dict[str, str | float | None] | None:
    if not boot_complete():
        return None
    try:
        import torch

        if not torch.cuda.is_available():
            return None
        props = torch.cuda.get_device_properties(0)
        return {
            "device": torch.cuda.get_device_name(0),
            "vram_gib": round(props.total_memory / (1024**3), 1),
            "vram_warning": _vram_warning,
        }
    except Exception:  # noqa: BLE001
        return None


def health_roles() -> dict[str, dict[str, str]]:
    config = get_registry().config
    return {
        role: {
            "model_id": config.spec_for(role).model_id,  # type: ignore[arg-type]
            "adapter": config.spec_for(role).adapter,  # type: ignore[arg-type]
        }
        for role in ("jailbreak", "domain", "pipeline")
    }


def health_models_loaded() -> list[dict[str, str]]:
    return [
        {"model_id": info.model_id, "adapter": info.adapter}
        for info in get_registry().list_loaded()
    ]


@contextmanager
def pipeline_session():
    global _classify_unavailable
    registry = get_registry()
    pipeline_id = registry.config.pipeline.model_id
    swapped_in = False
    evicted: list[HfModelId] = []

    with registry._lifecycle_lock:
        if not registry.is_loaded(pipeline_id):
            _classify_unavailable = True
            evicted = registry.evict_all(except_ids=frozenset())
            try:
                registry.ensure_loaded(pipeline_id)
                swapped_in = True
            except Exception:
                _classify_unavailable = False
                for model_id in evicted:
                    registry.ensure_loaded(model_id)
                raise

        try:
            yield RoleRouter(registry)
        finally:
            if swapped_in:
                registry.unload(pipeline_id)
                for model_id in evicted:
                    registry.ensure_loaded(model_id)
                _classify_unavailable = False
            clear_cuda_cache()
