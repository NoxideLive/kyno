"""Domain and jailbreak classifiers for CAPS Mathematics via multi-model gateway."""

from __future__ import annotations

from gateway_inference import (
    HistoryTurn,
    classify_domain_with_phi,
    classify_jailbreak_with_phi,
    classify_message_parallel,
    gateway_available,
    gateway_backend_name,
    gateway_unavailable_reason,
)


class JailbreakClassifier:
    @property
    def backend(self) -> str:
        if gateway_available():
            return gateway_backend_name()
        return "gateway-unavailable"

    def classify(self, text: str) -> dict:
        trimmed = text.strip()
        if not trimmed:
            return {
                "label": "safe",
                "confidence": 1.0,
                "backend": self.backend,
            }

        result = classify_jailbreak_with_phi(trimmed)
        if result is not None:
            return result

        reason = gateway_unavailable_reason() or "Gateway not loaded"
        raise RuntimeError(reason)


class DomainClassifier:
    @property
    def backend(self) -> str:
        if gateway_available():
            return gateway_backend_name()
        return "gateway-unavailable"

    def classify(
        self,
        text: str,
        history: list[HistoryTurn] | None = None,
    ) -> dict:
        trimmed = text.strip()
        if not trimmed:
            return {
                "label": "off_topic",
                "confidence": 1.0,
                "backend": self.backend,
            }

        result = classify_domain_with_phi(trimmed, history=history)
        if result is not None:
            return result

        reason = gateway_unavailable_reason() or "Gateway not loaded"
        raise RuntimeError(reason)


class MessageClassifier:
    @property
    def backend(self) -> str:
        if gateway_available():
            return gateway_backend_name()
        return "gateway-unavailable"

    def classify(
        self,
        text: str,
        history: list[HistoryTurn] | None = None,
    ) -> dict:
        trimmed = text.strip()
        if not trimmed:
            backend = self.backend
            return {
                "allowed": False,
                "blocked": True,
                "block_reason": "off_topic",
                "jailbreak": {
                    "label": "safe",
                    "confidence": 1.0,
                    "backend": backend,
                },
                "domain": {
                    "label": "off_topic",
                    "confidence": 1.0,
                    "backend": backend,
                },
                "backend": backend,
            }

        result = classify_message_parallel(trimmed, history=history)
        if result is not None:
            return result

        reason = gateway_unavailable_reason() or "Gateway not loaded"
        raise RuntimeError(reason)


def load_domain_spec_summary() -> str:
    from pathlib import Path

    spec_path = Path(__file__).resolve().parents[2] / "docs" / "domain-spec.md"
    if spec_path.is_file():
        return spec_path.read_text(encoding="utf-8")[:500]
    return "CAPS Mathematics Grades 1–12"
