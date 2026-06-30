"""FastAPI domain gateway for CAPS Mathematics."""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from classifier import DomainClassifier, load_domain_spec_summary
from phi_inference import phi_available, phi_unavailable_reason

THRESHOLD = float(os.environ.get("DOMAIN_CONFIDENCE_THRESHOLD", "0.55"))

# Blocking: label off_topic, or on_topic with confidence below THRESHOLD (low-confidence
# on_topic is flipped to off_topic before returning blocked=true).

app = FastAPI(title="Kyno Domain Gateway", version="1.0.0")
classifier = DomainClassifier()


class ClassifyRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)


class ClassifyResponse(BaseModel):
    label: str
    confidence: float
    backend: str
    blocked: bool


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "backend": classifier.backend,
        "phi_adapter_loaded": phi_available(),
        "phi_unavailable_reason": phi_unavailable_reason(),
        "threshold": THRESHOLD,
    }


@app.post("/classify/domain", response_model=ClassifyResponse)
def classify_domain(body: ClassifyRequest) -> ClassifyResponse:
    result = classifier.classify(body.text)
    label = result["label"]
    confidence = result["confidence"]

    if label == "on_topic" and confidence < THRESHOLD:
        label = "off_topic"

    return ClassifyResponse(
        label=label,
        confidence=confidence,
        backend=result["backend"],
        blocked=label == "off_topic",
    )


@app.get("/domain-spec")
def domain_spec() -> dict:
    return {"summary": load_domain_spec_summary()}
