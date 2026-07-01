"""FastAPI domain gateway for CAPS Mathematics."""

from __future__ import annotations

import asyncio
import contextlib
import os
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from auth import require_api_key
from classifier import (
    DomainClassifier,
    JailbreakClassifier,
    MessageClassifier,
    load_domain_spec_summary,
)
from compact_prompt_overlay import invalidate_overlay_cache, set_compact_test_mode
from domain_prompt import invalidate_prompt_cache, validate_prompt_data
from jailbreak_prompt import invalidate_jailbreak_prompt_cache
from gateway_inference import (
    GatewayInferenceError,
    PhiInferenceError,
    boot_complete,
    boot_gateway,
    gateway_available,
    gateway_backend_name,
    gateway_unavailable_reason,
    generate_text,
    gpu_device_info,
    health_models_loaded,
    health_roles,
    pipeline_session,
)
from inference.registry import get_registry
from pipeline.phases import ALL_PHASES, Phase
from pipeline.rebuild import load_last_report, rebuild
from pipeline.repo_paths import domain_dir, repo_root

_pipeline_lock = asyncio.Lock()
_pipeline_running = False
_boot_task: asyncio.Task[None] | None = None
_boot_failed = False
_classify_semaphore = asyncio.Semaphore(
    max(1, int(os.environ.get("PHI_CLASSIFY_CONCURRENCY", "1")))
)
jailbreak_classifier = JailbreakClassifier()
domain_classifier = DomainClassifier()
message_classifier = MessageClassifier()


async def _boot_gateway_background() -> None:
    global _boot_failed
    try:
        validate_prompt_data()
        await asyncio.to_thread(boot_gateway)
    except Exception as exc:  # noqa: BLE001
        _boot_failed = True
        print(f"Gateway boot failed: {exc}", flush=True)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _boot_task
    _boot_task = asyncio.create_task(_boot_gateway_background())
    yield
    if _boot_task is not None:
        _boot_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _boot_task


app = FastAPI(title="Kyno Domain Gateway", version="2.0.0", lifespan=lifespan)


class HistoryTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1)


class ClassifyRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)
    history: list[HistoryTurn] = Field(default_factory=list)


class StageResponse(BaseModel):
    label: str
    confidence: float
    backend: str


class ClassifyResponse(BaseModel):
    label: str
    confidence: float
    backend: str
    blocked: bool


class MessageClassifyResponse(BaseModel):
    allowed: bool
    blocked: bool
    block_reason: Literal["jailbreak_attempted", "off_topic"] | None
    jailbreak: StageResponse
    domain: StageResponse
    backend: str


class PipelineRebuildRequest(BaseModel):
    phases: list[Phase] | None = None


class ReloadPromptsRequest(BaseModel):
    compact_test: bool | None = None


class GenerateRequest(BaseModel):
    system: str = Field(..., min_length=1)
    user: str = Field(..., min_length=1)
    max_new_tokens: int = Field(default=1024, ge=1, le=4096)
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)


class GenerateResponse(BaseModel):
    text: str


def _require_gateway() -> None:
    if not gateway_available():
        raise HTTPException(
            status_code=503,
            detail=gateway_unavailable_reason() or "Gateway not loaded",
        )


def _classify_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (GatewayInferenceError, PhiInferenceError)):
        return HTTPException(
            status_code=503,
            detail=str(exc),
            headers={"Retry-After": "1"},
        )
    return HTTPException(status_code=503, detail=str(exc))


async def _run_classify(fn, *args, **kwargs):
    async with _classify_semaphore:
        return await asyncio.to_thread(fn, *args, **kwargs)


@app.get("/health")
def health():
    ready = boot_complete()
    profile = None
    roles = None
    models_loaded = None
    if ready:
        try:
            profile = get_registry().config.profile
            roles = health_roles()
            models_loaded = health_models_loaded()
        except RuntimeError:
            pass

    payload = {
        "status": "ok" if ready and gateway_available() else "starting",
        "backend": gateway_backend_name() if ready else "gateway-unavailable",
        "phi_loaded": gateway_available(),
        "phi_unavailable_reason": gateway_unavailable_reason(),
        "profile": profile,
        "roles": roles,
        "models_loaded": models_loaded,
        "gpu": gpu_device_info(),
        "repo_root": str(repo_root()),
        "domain_dir": str(domain_dir()),
        "pipeline_running": _pipeline_running,
    }
    if _boot_failed:
        return JSONResponse(status_code=503, content=payload)
    return payload


@app.post("/classify/message", response_model=MessageClassifyResponse)
async def classify_message(body: ClassifyRequest) -> MessageClassifyResponse:
    _require_gateway()

    history = [{"role": turn.role, "content": turn.content} for turn in body.history]
    try:
        result = await _run_classify(
            message_classifier.classify, body.text, history=history
        )
    except (GatewayInferenceError, PhiInferenceError, RuntimeError) as exc:
        raise _classify_http_error(exc) from exc

    return MessageClassifyResponse(
        allowed=bool(result["allowed"]),
        blocked=bool(result["blocked"]),
        block_reason=result.get("block_reason"),
        jailbreak=StageResponse(**result["jailbreak"]),
        domain=StageResponse(**result["domain"]),
        backend=str(result["backend"]),
    )


@app.post("/classify/jailbreak", response_model=ClassifyResponse)
async def classify_jailbreak(body: ClassifyRequest) -> ClassifyResponse:
    _require_gateway()

    try:
        result = await _run_classify(jailbreak_classifier.classify, body.text)
    except (GatewayInferenceError, PhiInferenceError, RuntimeError) as exc:
        raise _classify_http_error(exc) from exc

    label = result["label"]
    return ClassifyResponse(
        label=label,
        confidence=result["confidence"],
        backend=result["backend"],
        blocked=label == "jailbreak_attempted",
    )


@app.post("/classify/domain", response_model=ClassifyResponse)
async def classify_domain(body: ClassifyRequest) -> ClassifyResponse:
    _require_gateway()

    history = [{"role": turn.role, "content": turn.content} for turn in body.history]
    try:
        result = await _run_classify(
            domain_classifier.classify, body.text, history=history
        )
    except (GatewayInferenceError, PhiInferenceError, RuntimeError) as exc:
        raise _classify_http_error(exc) from exc

    label = result["label"]
    return ClassifyResponse(
        label=label,
        confidence=result["confidence"],
        backend=result["backend"],
        blocked=label != "on_topic",
    )


@app.get("/domain-spec")
def domain_spec() -> dict:
    return {"summary": load_domain_spec_summary()}


@app.post("/admin/reload-prompts", dependencies=[Depends(require_api_key)])
def reload_prompts(body: ReloadPromptsRequest | None = None) -> dict:
    if body is not None and body.compact_test is not None:
        set_compact_test_mode(body.compact_test)
    invalidate_overlay_cache()
    invalidate_prompt_cache()
    invalidate_jailbreak_prompt_cache()
    return {"ok": True, "compact_test": body.compact_test if body else None}


@app.post("/generate", response_model=GenerateResponse, dependencies=[Depends(require_api_key)])
async def generate(body: GenerateRequest) -> GenerateResponse:
    _require_gateway()
    try:
        text = await _run_classify(
            generate_text,
            system=body.system,
            user=body.user,
            max_new_tokens=body.max_new_tokens,
            temperature=body.temperature,
        )
    except (GatewayInferenceError, PhiInferenceError, RuntimeError) as exc:
        raise _classify_http_error(exc) from exc
    return GenerateResponse(text=text)


def _run_pipeline_rebuild(phases: list[Phase] | None) -> dict:
    with pipeline_session():
        return rebuild(phases)


@app.post("/pipeline/rebuild")
async def pipeline_rebuild(
    body: PipelineRebuildRequest | None = None,
    _: None = Depends(require_api_key),
):
    global _pipeline_running

    if not boot_complete():
        raise HTTPException(
            status_code=503,
            detail=gateway_unavailable_reason() or "Gateway not booted",
        )

    if _pipeline_running:
        raise HTTPException(status_code=409, detail="Pipeline rebuild already running")

    phases = body.phases if body else None
    if phases is not None:
        invalid = [p for p in phases if p not in ALL_PHASES]
        if invalid:
            raise HTTPException(status_code=400, detail=f"Invalid phases: {invalid}")

    async with _pipeline_lock:
        _pipeline_running = True
        try:
            report = await asyncio.to_thread(_run_pipeline_rebuild, phases)
        finally:
            _pipeline_running = False

    status = 200 if report.get("ok") else 207
    return JSONResponse(status_code=status, content=report)


@app.get("/pipeline/status")
def pipeline_status(_: None = Depends(require_api_key)) -> dict:
    report = load_last_report()
    if report is None:
        return {"status": "no_runs"}
    return report
