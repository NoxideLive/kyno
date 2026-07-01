"""Reload compact prompts on the running phi-gateway."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request


def _gateway_url() -> str:
    return os.environ.get("PHI_GATEWAY_URL", "http://localhost:8090").strip().rstrip("/")


def _api_key() -> str:
    key = os.environ.get("PHI_GATEWAY_API_KEY", "").strip()
    if not key:
        raise RuntimeError("PHI_GATEWAY_API_KEY is required for reload")
    return key


def check_health(*, expect_profile: str = "small") -> dict:
    url = f"{_gateway_url()}/health"
    with urllib.request.urlopen(url, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if payload.get("profile") != expect_profile:
        raise RuntimeError(
            f"Gateway profile={payload.get('profile')!r}, expected {expect_profile!r}"
        )
    if not payload.get("phi_loaded"):
        raise RuntimeError("Gateway phi_loaded=false")
    return payload


def reload_prompts(*, compact_test: bool | None = None) -> dict:
    url = f"{_gateway_url()}/admin/reload-prompts"
    payload: dict | None = None
    if compact_test is not None:
        payload = {"compact_test": compact_test}
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {_api_key()}",
            **({"Content-Type": "application/json"} if body is not None else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Reload failed HTTP {exc.code}: {body}") from exc


def reload_and_verify(*, expect_profile: str = "small") -> dict:
    health = check_health(expect_profile=expect_profile)
    result = reload_prompts()
    return {"health": health, "reload": result}


def load_api_key_from_env_file(path: str = ".env.local") -> None:
    """Set PHI_GATEWAY_API_KEY from .env.local if not already in environment."""
    if os.environ.get("PHI_GATEWAY_API_KEY"):
        return
    env_path = os.path.join(os.getcwd(), path)
    if not os.path.isfile(env_path):
        return
    with open(env_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line.startswith("PHI_GATEWAY_API_KEY="):
                _, _, value = line.partition("=")
                os.environ["PHI_GATEWAY_API_KEY"] = value.strip().strip('"').strip("'")
                return


def main_reload() -> int:
    load_api_key_from_env_file()
    try:
        payload = reload_and_verify()
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(payload, indent=2))
    return 0
