"""Timing and progress logging for domain training pipeline."""

from __future__ import annotations

import threading
import time
from typing import Any


class TimingTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._run_start = time.monotonic()
        self._phases: dict[str, float] = {}
        self._phase_starts: dict[str, float] = {}
        self._records: dict[str, list[float]] = {}

    def start_phase(self, name: str) -> None:
        with self._lock:
            self._phase_starts[name] = time.monotonic()

    def end_phase(self, name: str) -> float:
        with self._lock:
            start = self._phase_starts.pop(name, None)
            if start is None:
                return 0.0
            elapsed_ms = (time.monotonic() - start) * 1000
            self._phases[name] = self._phases.get(name, 0.0) + elapsed_ms
            return elapsed_ms

    def record(self, name: str, duration_ms: float) -> None:
        with self._lock:
            self._records.setdefault(name, []).append(duration_ms)

    def elapsed_s(self) -> float:
        return time.monotonic() - self._run_start

    def summary(self) -> dict[str, Any]:
        with self._lock:
            records_summary = {
                name: {
                    "count": len(values),
                    "total_ms": round(sum(values), 1),
                    "avg_ms": round(sum(values) / len(values), 1) if values else 0,
                }
                for name, values in self._records.items()
            }
            return {
                "total_wall_ms": round(self.elapsed_s() * 1000, 1),
                "phases_ms": {k: round(v, 1) for k, v in self._phases.items()},
                "records": records_summary,
            }


class GradeProgress:
    def __init__(self, grade: int, total_chunks: int) -> None:
        self.grade = grade
        self.total_chunks = total_chunks
        self._lock = threading.Lock()
        self._completed = 0
        self._start = time.monotonic()

    def tick(self) -> None:
        with self._lock:
            self._completed += 1

    @property
    def completed(self) -> int:
        with self._lock:
            return self._completed

    def format_line(self, rate_stats: dict[str, dict[str, Any]]) -> str:
        with self._lock:
            done = self._completed
        elapsed = time.monotonic() - self._start
        pct = (done / self.total_chunks * 100) if self.total_chunks else 100.0
        eta = 0.0
        if done > 0 and done < self.total_chunks:
            eta = elapsed / done * (self.total_chunks - done)

        parts = [
            f"Grade {self.grade}: chunk {done}/{self.total_chunks} ({pct:.0f}%)",
            f"{elapsed:.0f}s elapsed",
        ]
        if eta > 0:
            parts.append(f"ETA ~{eta:.0f}s")

        for model, stats in rate_stats.items():
            short = model.split("/")[-1][:12]
            wait_s = stats.get("wait_ms", 0) / 1000
            retries = stats.get("retries", 0)
            parts.append(f"{short} wait {wait_s:.1f}s")
            if retries:
                parts.append(f"429×{stats.get('rate_limit_429', retries)}")

        return " | ".join(parts)
