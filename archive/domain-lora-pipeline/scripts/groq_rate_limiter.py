"""Per-model Groq rate limiting with header-aware throttling and stats."""

from __future__ import annotations

import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

MODEL_LIMITS: dict[str, dict[str, int]] = {
    "openai/gpt-oss-120b": {"rpm": 30, "tpm": 8000},
    "openai/gpt-oss-20b": {"rpm": 30, "tpm": 8000},
    "llama-3.1-8b-instant": {"rpm": 30, "tpm": 6000},
}

DEFAULT_RPM = 30
DEFAULT_TPM = 8000
RPM_SAFETY_MARGIN = 2
MIN_TOKENS_BUFFER = 800


def parse_reset_seconds(value: str) -> float:
    """Parse Groq reset headers like '7.66s' or '2m59.56s'."""
    value = value.strip().lower()
    if not value:
        return 1.0
    match = re.match(r"^(\d+(?:\.\d+)?)s$", value)
    if match:
        return float(match.group(1))
    match = re.match(r"^(\d+)m(\d+(?:\.\d+)?)s$", value)
    if match:
        return int(match.group(1)) * 60 + float(match.group(2))
    try:
        return float(value)
    except ValueError:
        return 1.0


@dataclass
class ModelBucketStats:
    requests: int = 0
    retries: int = 0
    rate_limit_waits: int = 0
    rate_limit_429: int = 0
    total_wait_ms: float = 0.0
    last_remaining_tokens: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "requests": self.requests,
            "retries": self.retries,
            "rate_limit_waits": self.rate_limit_waits,
            "rate_limit_429": self.rate_limit_429,
            "wait_ms": round(self.total_wait_ms, 1),
            "last_remaining_tokens": self.last_remaining_tokens,
        }


@dataclass
class ModelBucket:
    model: str
    rpm_limit: int
    tpm_limit: int
    request_times: deque[float] = field(default_factory=deque)
    remaining_tokens: int | None = None
    reset_tokens_at: float = 0.0
    stats: ModelBucketStats = field(default_factory=ModelBucketStats)


class GroqRateLimiter:
    """Thread-safe limiter with separate buckets per model id."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buckets: dict[str, ModelBucket] = {}

    def _bucket(self, model: str) -> ModelBucket:
        if model not in self._buckets:
            limits = MODEL_LIMITS.get(model, {"rpm": DEFAULT_RPM, "tpm": DEFAULT_TPM})
            self._buckets[model] = ModelBucket(
                model=model,
                rpm_limit=limits["rpm"],
                tpm_limit=limits["tpm"],
            )
        return self._buckets[model]

    def _sleep(self, bucket: ModelBucket, seconds: float, *, reason: str) -> None:
        if seconds <= 0:
            return
        bucket.stats.rate_limit_waits += 1
        bucket.stats.total_wait_ms += seconds * 1000
        time.sleep(seconds)

    def acquire(self, model: str, *, estimated_tokens: int = 2000) -> None:
        with self._lock:
            bucket = self._bucket(model)
            now = time.monotonic()

            rpm_cap = max(1, bucket.rpm_limit - RPM_SAFETY_MARGIN)
            while bucket.request_times and now - bucket.request_times[0] >= 60.0:
                bucket.request_times.popleft()
            if len(bucket.request_times) >= rpm_cap:
                wait = 60.0 - (now - bucket.request_times[0]) + 0.05
                self._sleep(bucket, wait, reason="rpm")
                now = time.monotonic()
                while bucket.request_times and now - bucket.request_times[0] >= 60.0:
                    bucket.request_times.popleft()

            if (
                bucket.remaining_tokens is not None
                and bucket.remaining_tokens < max(MIN_TOKENS_BUFFER, estimated_tokens)
                and bucket.reset_tokens_at > now
            ):
                self._sleep(bucket, bucket.reset_tokens_at - now + 0.05, reason="tpm")

    def record_request(self, model: str) -> None:
        with self._lock:
            bucket = self._bucket(model)
            bucket.request_times.append(time.monotonic())
            bucket.stats.requests += 1

    def update_from_response(self, model: str, headers: dict[str, str]) -> None:
        with self._lock:
            bucket = self._bucket(model)
            remaining = headers.get("x-ratelimit-remaining-tokens")
            reset = headers.get("x-ratelimit-reset-tokens")
            if remaining is not None:
                try:
                    bucket.remaining_tokens = int(remaining)
                    bucket.stats.last_remaining_tokens = bucket.remaining_tokens
                except ValueError:
                    pass
            if reset:
                bucket.reset_tokens_at = time.monotonic() + parse_reset_seconds(reset)

    def record_retry(self, model: str, *, is_429: bool = False) -> None:
        with self._lock:
            bucket = self._bucket(model)
            bucket.stats.retries += 1
            if is_429:
                bucket.stats.rate_limit_429 += 1

    def record_wait(self, model: str, seconds: float) -> None:
        with self._lock:
            bucket = self._bucket(model)
            bucket.stats.rate_limit_waits += 1
            bucket.stats.total_wait_ms += seconds * 1000

    def stats_for_model(self, model: str) -> dict[str, Any]:
        with self._lock:
            return self._bucket(model).stats.to_dict()

    def all_stats(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {model: b.stats.to_dict() for model, b in self._buckets.items()}

    def reset_stats(self) -> None:
        with self._lock:
            for bucket in self._buckets.values():
                bucket.stats = ModelBucketStats()


_global_limiter = GroqRateLimiter()


def get_rate_limiter() -> GroqRateLimiter:
    return _global_limiter
