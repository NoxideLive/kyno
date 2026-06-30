"""Domain classifier for CAPS Mathematics (Gr 1–12).

Backend priority (per Phi setup):
  1. Phi-4-mini-instruct + domain LoRA adapter (phi_inference)
  2. sklearn TF-IDF model (train.py)
  3. token log-odds (train_simple.py)
  4. keyword rules
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from phi_inference import classify_with_phi, phi_available, phi_unavailable_reason

try:
    import joblib
except ImportError:
    joblib = None  # type: ignore[assignment]

MODEL_DIR = Path(__file__).resolve().parent / "models"
SKLEARN_MODEL_PATH = MODEL_DIR / "domain_classifier.joblib"
TOKEN_WEIGHTS_PATH = MODEL_DIR / "token_weights.json"

HYBRID_OVERRIDE_CONFIDENCE = 0.85

ON_TOPIC_PATTERNS = [
    r"\bcaps mathematics\b",
    r"\bcaps maths\b",
    r"\bcaps wiskunde\b",
    r"\batp\b",
    r"\bannual teaching plan\b",
    r"\bmathematics\b",
    r"\bmaths\b",
    r"\bwiskunde\b",
    r"\bgrade\s*\d{1,2}\b",
    r"\bgraad\s*\d{1,2}\b",
    r"\bsyllabus\b",
    r"\bcurriculum\b",
    r"\bexam\b",
    r"\bassessment\b",
    r"\bworksheet\b",
    r"\blesson plan\b",
    r"\bteaching plan\b",
    r"\bstudy help\b",
    r"\bfraction",
    r"\balgebra\b",
    r"\bgeometry\b",
    r"\bcalculus\b",
    r"\btrigonometry\b",
    r"\bplace value\b",
    r"\bwhole number",
]

OFF_TOPIC_PATTERNS = [
    r"\bmathematical literacy\b",
    r"\bwiskundige geletterdheid\b",
    r"\blife orientation\b",
    r"\bnatural science",
    r"\bhistory\b",
    r"\bgeography\b",
    r"\bpython\b",
    r"\bjavascript\b",
    r"\breact\b",
    r"\bweather\b",
    r"\bcape town\b",
    r"\bib mathematics\b",
    r"\bcambridge\b",
    r"\bigcse\b",
    r"\brelationship advice\b",
    r"\bmedical\b",
    r"\blegal advice\b",
    r"\bworld war\b",
    r"\bhome language\b",
    r"\bpoetry analysis\b",
    r"\bpeanut",
]

HOMOGRAPH_PATTERNS = [
    re.compile(r"\bpeanut", re.IGNORECASE),
]

TYPOGRAPHY_CAPS_PATTERNS = [
    re.compile(r"^caps?$", re.IGNORECASE),
    re.compile(r"^all caps$", re.IGNORECASE),
    re.compile(r"^write in caps$", re.IGNORECASE),
    re.compile(r"^don't type in caps$", re.IGNORECASE),
    re.compile(r"^uppercase$", re.IGNORECASE),
]


def is_typography_caps(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    for pattern in TYPOGRAPHY_CAPS_PATTERNS:
        if pattern.search(stripped):
            return True
    lower = stripped.lower()
    if lower in {"caps", "cap"} and not re.search(
        r"\b(caps mathematics|caps maths|caps wiskunde|what is caps|grade\s*\d)\b",
        lower,
    ):
        return True
    return False


def apply_hybrid_overrides(text: str, result: dict) -> dict:
    """Post-Phi corrections for known production failure modes."""
    lower = text.lower().strip()
    label = result["label"]
    confidence = float(result["confidence"])
    backend = result.get("backend", "phi-lora")

    if is_typography_caps(text):
        return {
            "label": "off_topic",
            "confidence": max(confidence, 0.9),
            "backend": f"{backend}+hybrid",
        }

    for pattern in HOMOGRAPH_PATTERNS:
        if pattern.search(text):
            return {
                "label": "off_topic",
                "confidence": max(confidence, 0.9),
                "backend": f"{backend}+hybrid",
            }

    off_score = sum(2 for p in OFF_TOPIC_PATTERNS if re.search(p, lower))
    if off_score > 0:
        return {
            "label": "off_topic",
            "confidence": max(confidence, 0.85),
            "backend": f"{backend}+hybrid",
        }

    on_score = sum(1 for p in ON_TOPIC_PATTERNS if re.search(p, lower))
    if label == "off_topic" and on_score > 0 and confidence < HYBRID_OVERRIDE_CONFIDENCE:
        return {
            "label": "on_topic",
            "confidence": max(confidence, 0.65),
            "backend": f"{backend}+hybrid",
        }

    return result


class DomainClassifier:
    def __init__(self) -> None:
        self._sklearn_model = None
        self._token_model: dict | None = None
        if SKLEARN_MODEL_PATH.is_file() and joblib is not None:
            self._sklearn_model = joblib.load(SKLEARN_MODEL_PATH)
        elif TOKEN_WEIGHTS_PATH.is_file():
            self._token_model = json.loads(
                TOKEN_WEIGHTS_PATH.read_text(encoding="utf-8")
            )

    @property
    def backend(self) -> str:
        if phi_available():
            return "phi-lora"
        if self._sklearn_model is not None:
            return "sklearn"
        if self._token_model is not None:
            return "token_log_odds"
        return "keywords"

    def classify(self, text: str) -> dict:
        trimmed = text.strip()
        if not trimmed:
            return {
                "label": "off_topic",
                "confidence": 1.0,
                "backend": self.backend,
            }

        phi_result = classify_with_phi(trimmed)
        if phi_result is not None:
            return apply_hybrid_overrides(trimmed, phi_result)

        if self._sklearn_model is not None:
            pipeline = self._sklearn_model
            proba = pipeline.predict_proba([trimmed])[0]
            classes = list(pipeline.classes_)
            on_idx = classes.index("on_topic")
            off_idx = classes.index("off_topic")
            if proba[on_idx] >= proba[off_idx]:
                result = {
                    "label": "on_topic",
                    "confidence": float(proba[on_idx]),
                    "backend": "sklearn",
                }
            else:
                result = {
                    "label": "off_topic",
                    "confidence": float(proba[off_idx]),
                    "backend": "sklearn",
                }
            return apply_hybrid_overrides(trimmed, result)

        if self._token_model is not None:
            return apply_hybrid_overrides(trimmed, _token_classify(trimmed, self._token_model))

        return apply_hybrid_overrides(trimmed, _keyword_classify(trimmed))


def _token_classify(text: str, model: dict) -> dict:
    import math

    token_pattern = re.compile(r"[a-z0-9]+")
    tokens = token_pattern.findall(text.lower())
    score_on = model.get("bias_on", 0.0)
    weights = model.get("weights", {})
    for token in tokens:
        score_on += weights.get(token, 0.0)
    confidence_on = 1.0 / (1.0 + math.exp(-score_on))
    if confidence_on >= 0.5:
        return {
            "label": "on_topic",
            "confidence": confidence_on,
            "backend": "token_log_odds",
        }
    return {
        "label": "off_topic",
        "confidence": 1.0 - confidence_on,
        "backend": "token_log_odds",
    }


def _keyword_classify(text: str) -> dict:
    lower = text.lower()
    if is_typography_caps(text):
        return {"label": "off_topic", "confidence": 0.9, "backend": "keywords"}

    on_score = sum(1 for p in ON_TOPIC_PATTERNS if re.search(p, lower))
    off_score = sum(2 for p in OFF_TOPIC_PATTERNS if re.search(p, lower))

    if off_score > on_score:
        confidence = min(0.95, 0.55 + off_score * 0.1)
        return {"label": "off_topic", "confidence": confidence, "backend": "keywords"}

    if on_score > 0:
        confidence = min(0.95, 0.55 + on_score * 0.08)
        return {"label": "on_topic", "confidence": confidence, "backend": "keywords"}

    return {"label": "off_topic", "confidence": 0.6, "backend": "keywords"}


def load_domain_spec_summary() -> str:
    spec_path = Path(__file__).resolve().parents[2] / "docs" / "domain-spec.md"
    if spec_path.is_file():
        return spec_path.read_text(encoding="utf-8")[:500]
    return "CAPS Mathematics Grades 1–12"
