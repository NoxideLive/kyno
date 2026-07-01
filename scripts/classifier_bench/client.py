"""Gateway HTTP client for bench runs."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from typing import Any

_thread_local = threading.local()


def _session() -> urllib.request.OpenerDirector:
    opener = getattr(_thread_local, "opener", None)
    if opener is None:
        opener = urllib.request.build_opener()
        _thread_local.opener = opener
    return opener


def _make_request(url: str, body: bytes) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )


def post_json(
    gateway_url: str,
    path: str,
    payload: dict[str, Any],
    *,
    timeout: float = 120.0,
    max_retries: int = 8,
) -> dict[str, Any]:
    url = f"{gateway_url.rstrip('/')}{path}"
    body = json.dumps(payload).encode("utf-8")
    opener = _session()
    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            with opener.open(_make_request(url, body), timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last_error = exc
            exc.read()
            if exc.code == 503 and attempt < max_retries - 1:
                time.sleep(0.5 * (attempt + 1))
                continue
            raise
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt < max_retries - 1:
                time.sleep(0.5 * (attempt + 1))
                continue
            raise
    if last_error is not None:
        raise last_error
    raise RuntimeError("post_json failed without error")
