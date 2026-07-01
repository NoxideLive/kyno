"""API key auth for admin pipeline routes."""

from __future__ import annotations

import os

from fastapi import Header, HTTPException


def require_api_key(authorization: str | None = Header(default=None)) -> None:
    expected = os.environ.get("PHI_GATEWAY_API_KEY", "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="PHI_GATEWAY_API_KEY not configured on gateway",
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if token != expected:
        raise HTTPException(status_code=403, detail="Invalid API key")
