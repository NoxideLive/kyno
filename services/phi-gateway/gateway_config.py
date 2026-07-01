"""Gateway profile presets and HuggingFace model role configuration."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Literal

ProfileName = Literal["small", "medium", "large"]
GatewayRole = Literal["jailbreak", "domain", "pipeline"]
AdapterKind = Literal["guard", "decoder"]
PromptVariant = Literal["full", "compact"]
HfModelId = str

QWEN_1_5B = "Qwen/Qwen2.5-1.5B-Instruct"
PHI_4_MINI = "microsoft/Phi-4-mini-instruct"
LLAMA_GUARD_3_1B = "meta-llama/Llama-Guard-3-1B"

PROFILE_PRESETS: dict[ProfileName, dict[GatewayRole, HfModelId]] = {
    "small": {
        "jailbreak": QWEN_1_5B,
        "domain": QWEN_1_5B,
        "pipeline": QWEN_1_5B,
    },
    "medium": {
        "jailbreak": PHI_4_MINI,
        "domain": PHI_4_MINI,
        "pipeline": PHI_4_MINI,
    },
    "large": {
        "jailbreak": LLAMA_GUARD_3_1B,
        "domain": PHI_4_MINI,
        "pipeline": PHI_4_MINI,
    },
}

_ROLE_ENV: dict[GatewayRole, str] = {
    "jailbreak": "PHI_GATEWAY_JAILBREAK_MODEL",
    "domain": "PHI_GATEWAY_DOMAIN_MODEL",
    "pipeline": "PHI_GATEWAY_PIPELINE_MODEL",
}

_GUARD_PATTERN = re.compile(r"(?i)(llama-?guard|shieldgemma|qwen.*guard|wildguard|prompt-?guard)")


@dataclass(frozen=True)
class RoleModelSpec:
    model_id: HfModelId
    adapter: AdapterKind


@dataclass(frozen=True)
class GatewayRoleConfig:
    profile: ProfileName
    jailbreak: RoleModelSpec
    domain: RoleModelSpec
    pipeline: RoleModelSpec

    def model_for(self, role: GatewayRole) -> HfModelId:
        return getattr(self, role).model_id

    def spec_for(self, role: GatewayRole) -> RoleModelSpec:
        return getattr(self, role)

    def classify_model_ids(self) -> frozenset[HfModelId]:
        return frozenset({self.jailbreak.model_id, self.domain.model_id})

    def all_model_ids(self) -> frozenset[HfModelId]:
        return frozenset(
            {self.jailbreak.model_id, self.domain.model_id, self.pipeline.model_id}
        )


def _parse_guard_models_env() -> frozenset[HfModelId]:
    raw = os.environ.get("PHI_GATEWAY_GUARD_MODELS", "").strip()
    if not raw:
        return frozenset()
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


def _normalize_profile(raw: str) -> ProfileName:
    value = raw.strip().lower()
    if value not in PROFILE_PRESETS:
        allowed = ", ".join(PROFILE_PRESETS)
        raise ValueError(f"Invalid PHI_GATEWAY_PROFILE={raw!r}; expected one of: {allowed}")
    return value  # type: ignore[return-value]


def _env_model_id(role: GatewayRole, preset: HfModelId) -> HfModelId:
    env_name = _ROLE_ENV[role]
    override = os.environ.get(env_name, "").strip()
    return override or preset


def looks_like_guard_model(model_id: HfModelId) -> bool:
    return _GUARD_PATTERN.search(model_id) is not None


def resolve_adapter(model_id: HfModelId) -> AdapterKind:
    if model_id in _parse_guard_models_env():
        return "guard"
    if looks_like_guard_model(model_id):
        return "guard"
    return "decoder"


def _role_spec(model_id: HfModelId) -> RoleModelSpec:
    if not model_id or "/" not in model_id:
        raise ValueError(f"Invalid HuggingFace model_id {model_id!r}; expected org/name")
    return RoleModelSpec(model_id=model_id, adapter=resolve_adapter(model_id))


def resolve_gateway_config() -> GatewayRoleConfig:
    profile = _normalize_profile(os.environ.get("PHI_GATEWAY_PROFILE", "medium"))
    preset = PROFILE_PRESETS[profile]
    config = GatewayRoleConfig(
        profile=profile,
        jailbreak=_role_spec(_env_model_id("jailbreak", preset["jailbreak"])),
        domain=_role_spec(_env_model_id("domain", preset["domain"])),
        pipeline=_role_spec(_env_model_id("pipeline", preset["pipeline"])),
    )
    validate_gateway_config(config)
    return config


def resolve_classify_prompt_variant(profile: ProfileName) -> PromptVariant:
    """Prompt density for decoder classify stages. Small profile defaults to compact."""
    raw = os.environ.get("PHI_GATEWAY_PROMPT_VARIANT", "").strip().lower()
    if raw in ("full", "compact"):
        return raw  # type: ignore[return-value]
    if raw and raw != "auto":
        raise ValueError(
            f"Invalid PHI_GATEWAY_PROMPT_VARIANT={raw!r}; expected full, compact, or auto"
        )
    return "compact" if profile == "small" else "full"


def validate_gateway_config(config: GatewayRoleConfig) -> None:
    if config.jailbreak.adapter not in ("guard", "decoder"):
        raise ValueError(f"Unsupported jailbreak adapter for {config.jailbreak.model_id}")

    for role in ("domain", "pipeline"):
        spec = config.spec_for(role)  # type: ignore[arg-type]
        if spec.adapter != "decoder":
            raise ValueError(
                f"Role {role} requires a decoder (causal LM) model; "
                f"{spec.model_id} resolved to adapter={spec.adapter!r}"
            )
