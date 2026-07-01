"""Domain gateway model configuration (resolved at runtime from gateway_config)."""

from __future__ import annotations

from gateway_config import PHI_4_MINI, resolve_gateway_config

PHI_MODEL_ID = PHI_4_MINI


def default_backend_name() -> str:
    return resolve_gateway_config().jailbreak.model_id
