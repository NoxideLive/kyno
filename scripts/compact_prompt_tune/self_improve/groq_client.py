"""Groq API client — strict json_schema structured outputs only."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from compact_prompt_tune.self_improve.log import debug, info, warn
from compact_prompt_tune.self_improve.prompts import phase_json_instruction

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_USER_AGENT = "kyno-self-improve/1.0"
MAX_RETRIES = 5
# Groq gpt-oss-20b: API default max_completion_tokens=1024; platform max output=65536
DEFAULT_MAX_COMPLETION_TOKENS = 8192
MAX_COMPLETION_TOKENS_CAP = 16384


def groq_reasoning_effort() -> str:
    return os.environ.get("SELF_IMPROVE_GROQ_REASONING_EFFORT", "medium").strip()


def groq_model() -> str:
    return os.environ.get("SELF_IMPROVE_GROQ_MODEL", "openai/gpt-oss-20b").strip()


def groq_api_key() -> str:
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GROQ_API_KEY is required for self-improve propose phases")
    return key


def load_groq_key_from_env_file(path: str = ".env.local") -> None:
    if os.environ.get("GROQ_API_KEY"):
        return
    env_path = Path(path)
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("GROQ_API_KEY="):
                _, _, value = line.partition("=")
                os.environ["GROQ_API_KEY"] = value.strip().strip('"').strip("'")
                return
    _load_groq_key_from_convex()


def _load_groq_key_from_convex() -> None:
    """Fallback: read GROQ_API_KEY from Convex env (same as test-widget-prompts.ts)."""
    if os.environ.get("GROQ_API_KEY"):
        return
    import subprocess

    root = Path(__file__).resolve().parents[3]
    env = os.environ.copy()
    if env.get("CONVEX_DEPLOYMENT"):
        env["CONVEX_DEPLOYMENT"] = env["CONVEX_DEPLOYMENT"].split("#")[0].strip()
    try:
        result = subprocess.run(
            ["npx", "convex", "env", "get", "GROQ_API_KEY"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return
    key = result.stdout.strip()
    if result.returncode == 0 and key:
        os.environ["GROQ_API_KEY"] = key


def _escape_newlines_in_json_strings(candidate: str) -> str:
    out: list[str] = []
    in_string = False
    escape = False
    for ch in candidate:
        if escape:
            out.append(ch)
            escape = False
            continue
        if ch == "\\":
            out.append(ch)
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            out.append(ch)
            continue
        if in_string and ch == "\n":
            out.append("\\n")
            continue
        if in_string and ch == "\r":
            continue
        if in_string and ch == "\t":
            out.append("\\t")
            continue
        out.append(ch)
    return "".join(out)


def parse_json_content(raw: str) -> dict[str, Any]:
    stripped = raw.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", stripped)
    if fence:
        stripped = fence.group(1).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end <= start:
        raise ValueError(f"No JSON object in response: {raw[:400]!r}")
    candidate = stripped[start : end + 1]
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        parsed = json.loads(_escape_newlines_in_json_strings(candidate))
    if not isinstance(parsed, dict):
        raise ValueError("Expected JSON object")
    return parsed


def _parse_groq_http_error(detail: str) -> tuple[str, str | None]:
    """Return (message, failed_generation) from Groq error JSON body."""
    try:
        payload = json.loads(detail)
        err = payload.get("error") or {}
        message = str(err.get("message", detail))
        failed = err.get("failed_generation")
        return message, str(failed) if failed is not None else None
    except json.JSONDecodeError:
        return detail, None


class GroqRequestError(RuntimeError):
    def __init__(self, message: str, *, failed_generation: str | None = None) -> None:
        super().__init__(message)
        self.failed_generation = failed_generation


def _post_groq(body: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    started = time.monotonic()
    req = urllib.request.Request(
        GROQ_CHAT_URL,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {groq_api_key()}",
            "Content-Type": "application/json",
            "User-Agent": GROQ_USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        message, failed_generation = _parse_groq_http_error(detail)
        raise GroqRequestError(
            f"Groq HTTP {exc.code}: {message}",
            failed_generation=failed_generation,
        ) from exc

    latency_ms = int((time.monotonic() - started) * 1000)
    content = (
        payload.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )
    if not content:
        raise GroqRequestError("Groq returned empty content")
    usage = payload.get("usage") or {}
    debug(
        "Groq response %dms model=%s tokens=%s chars=%d",
        latency_ms,
        body.get("model"),
        usage,
        len(content),
    )
    return content, usage


def _build_correction_message(
    *,
    schema_name: str,
    error_message: str,
    failed_generation: str | None,
) -> str:
    parts = [
        "Your previous response did not satisfy the required JSON schema.",
        f"Error: {error_message}",
        phase_json_instruction(schema_name),
        "Output ONLY the JSON object. No markdown fences, no prose, no reasoning text.",
    ]
    if failed_generation:
        parts.append(f"Invalid partial output was: {failed_generation[:1200]}")
    return "\n".join(parts)


def groq_thread_turn(
    *,
    messages: list[dict[str, str]],
    response_schema: dict[str, Any],
    schema_name: str,
    max_completion_tokens: int,
    temperature: float = 0.1,
) -> tuple[str, dict[str, Any], list[dict[str, str]]]:
    """Run one Groq turn with strict json_schema retries. Returns (raw, parsed, messages)."""
    working = list(messages)
    last_error: Exception | None = None
    token_budget = max_completion_tokens
    reasoning = groq_reasoning_effort()

    for attempt in range(MAX_RETRIES):
        if attempt == 0:
            info(
                "Groq %s: model=%s max_completion_tokens=%d strict json_schema reasoning=%s",
                schema_name,
                groq_model(),
                token_budget,
                reasoning,
            )
        else:
            warn("Groq %s: retry %d/%d (strict json_schema)", schema_name, attempt + 1, MAX_RETRIES)

        body: dict[str, Any] = {
            "model": groq_model(),
            "messages": working,
            "temperature": temperature,
            "max_completion_tokens": token_budget,
            "stream": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": response_schema,
                },
            },
            "reasoning_effort": reasoning,
            # gpt-oss-20b: reasoning_format unsupported; exclude reasoning from response
            "include_reasoning": False,
        }

        try:
            content, _usage = _post_groq(body)
            parsed = parse_json_content(content)
            updated = working + [{"role": "assistant", "content": content}]
            info("Groq %s: ok", schema_name)
            return content, parsed, updated
        except GroqRequestError as exc:
            last_error = exc
            warn("Groq %s: attempt %d failed: %s", schema_name, attempt + 1, exc)
            if "max completion tokens" in str(exc).lower() or "token" in str(exc).lower():
                next_budget = min(token_budget + 4096, MAX_COMPLETION_TOKENS_CAP)
                if next_budget > token_budget:
                    token_budget = next_budget
                    info(
                        "Groq %s: raising max_completion_tokens to %d",
                        schema_name,
                        token_budget,
                    )
            if attempt + 1 < MAX_RETRIES:
                working = working + [
                    {
                        "role": "user",
                        "content": _build_correction_message(
                            schema_name=schema_name,
                            error_message=str(exc),
                            failed_generation=exc.failed_generation,
                        ),
                    }
                ]
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            warn("Groq %s: attempt %d failed: %s", schema_name, attempt + 1, exc)

    raise RuntimeError(f"Groq turn failed after {MAX_RETRIES} attempts: {last_error}")


def save_messages(path: Path, messages: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for msg in messages:
            fh.write(json.dumps(msg) + "\n")


def load_messages(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    rows: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows
