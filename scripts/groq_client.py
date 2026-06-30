"""Shared Groq chat client for local training-data scripts."""

from __future__ import annotations

import json
import os
import random
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from groq_rate_limiter import GroqRateLimiter, get_rate_limiter

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_EXTRACT_MODEL = "openai/gpt-oss-120b"
DEFAULT_GENERATE_MODEL = "openai/gpt-oss-20b"
DEFAULT_MODEL = DEFAULT_GENERATE_MODEL

RETRYABLE_STATUS = {408, 409, 429, 500, 502, 503, 504}
NON_RETRYABLE_STATUS = {400, 401, 403, 422}


class GroqApiError(RuntimeError):
    def __init__(self, status: int, detail: str, headers: dict[str, str] | None = None):
        super().__init__(f"Groq HTTP {status}: {detail}")
        self.status = status
        self.detail = detail
        self.headers = headers or {}


def load_groq_api_key() -> str:
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if key:
        return key

    for env_path in (Path(".env.local"), Path(".env")):
        if not env_path.is_file():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("GROQ_API_KEY="):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                if value:
                    return value

    raise RuntimeError(
        "GROQ_API_KEY not set. Export it or add to .env.local"
    )


def _estimate_tokens(system: str, user: str) -> int:
    return max(500, (len(system) + len(user)) // 4)


def _parse_retry_after(headers: dict[str, str]) -> float | None:
    raw = headers.get("retry-after")
    if not raw:
        return None
    try:
        return float(raw.strip())
    except ValueError:
        return None


def _backoff_seconds(attempt: int, headers: dict[str, str]) -> float:
    retry_after = _parse_retry_after(headers)
    if retry_after is not None:
        return retry_after
    base = min(32.0, 2.0 ** attempt)
    return base + random.uniform(0, 1)


def _http_chat_completion(
    *,
    api_key: str,
    body: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, str], float]:
    request = urllib.request.Request(
        GROQ_CHAT_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "kyno-training-scripts/1.0",
        },
        method="POST",
    )
    start = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8"))
            headers = {k.lower(): v for k, v in response.headers.items()}
            latency_ms = (time.monotonic() - start) * 1000
            return payload, headers, latency_ms
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        headers = {k.lower(): v for k, v in exc.headers.items()} if exc.headers else {}
        raise GroqApiError(exc.code, detail, headers) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Groq connection error: {exc.reason}") from exc


def chat_completion(
    *,
    system: str,
    user: str,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.2,
    max_retries: int = 5,
    limiter: GroqRateLimiter | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Call Groq chat completions with rate limiting and retries."""
    if limiter is None:
        limiter = get_rate_limiter()

    api_key = load_groq_api_key()
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    estimated = _estimate_tokens(system, user)
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        limiter.acquire(model, estimated_tokens=estimated)
        limiter.record_request(model)
        try:
            payload, headers, latency_ms = _http_chat_completion(api_key=api_key, body=body)
            limiter.update_from_response(model, headers)
            return payload, {
                "model": model,
                "latency_ms": round(latency_ms, 1),
                "headers": {
                    "remaining_tokens": headers.get("x-ratelimit-remaining-tokens"),
                    "reset_tokens": headers.get("x-ratelimit-reset-tokens"),
                },
            }
        except GroqApiError as exc:
            last_error = exc
            if exc.status in NON_RETRYABLE_STATUS or attempt >= max_retries:
                raise RuntimeError(str(exc)) from exc

            if exc.status not in RETRYABLE_STATUS:
                raise RuntimeError(str(exc)) from exc

            limiter.record_retry(model, is_429=(exc.status == 429))
            wait = _backoff_seconds(attempt, exc.headers)
            limiter.record_wait(model, wait)
            time.sleep(wait)
        except RuntimeError as exc:
            last_error = exc
            if attempt >= max_retries:
                raise
            limiter.record_retry(model, is_429=False)
            wait = _backoff_seconds(attempt, {})
            limiter.record_wait(model, wait)
            time.sleep(wait)

    if last_error:
        raise RuntimeError(str(last_error))
    raise RuntimeError("Groq request failed after retries")


def chat_json(
    *,
    system: str,
    user: str,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.2,
    max_retries: int = 5,
    limiter: GroqRateLimiter | None = None,
) -> dict[str, Any]:
    """Call Groq with json_object response and parse the result."""
    payload, _meta = chat_completion(
        system=system,
        user=user,
        model=model,
        temperature=temperature,
        max_retries=max_retries,
        limiter=limiter,
    )

    content = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
    if not content:
        raise RuntimeError("Groq returned empty content")

    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)

    return json.loads(content)
