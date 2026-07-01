"""Parallel bench runner."""

from __future__ import annotations

import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from typing import Any

from classifier_bench.client import post_json
from classifier_bench.load import BenchCase, BenchSuite
from classifier_bench.metrics import CaseResult, build_report


def _expected_actual(suite: str, case: BenchCase, response: dict[str, Any]) -> tuple[str, str, float | None, str | None]:
    if suite == "switch":
        expected = "allowed" if case.label == "allowed" else "blocked"
        actual = "allowed" if response.get("allowed") else "blocked"
        confidence = None
        block_reason = response.get("block_reason")
        if response.get("domain"):
            confidence = float(response["domain"].get("confidence", 0.0))
        return expected, actual, confidence, block_reason

    expected = case.label
    actual = str(response.get("label", ""))
    confidence = float(response.get("confidence", 0.0))
    return expected, actual, confidence, None


def _payload_for_case(case: BenchCase) -> dict[str, Any]:
    if case.suite == "jailbreak":
        return {"text": case.text}
    return {"text": case.text, "history": case.history}


def resolve_workers(requested: int, total_cases: int, config: dict) -> int:
    max_workers = int(config.get("max_workers", 4))
    default_workers = int(config.get("default_workers", 2))
    if requested <= 0:
        workers = min(total_cases, default_workers)
    else:
        workers = requested
    return max(1, min(workers, max_workers, total_cases))


def _classify_case(gateway_url: str, case: BenchCase, endpoint: str) -> CaseResult:
    response = post_json(gateway_url, endpoint, _payload_for_case(case))
    expected, actual, confidence, block_reason = _expected_actual(case.suite, case, response)
    return CaseResult(
        id=case.id,
        suite=case.suite,
        label=case.label,
        text=case.text,
        expected=expected,
        actual=actual,
        confidence=confidence,
        block_reason=block_reason,
        ok=expected == actual,
        meta=case.meta,
    )


def run_bench(
    *,
    gateway_url: str,
    suites: list[BenchSuite],
    workers: int,
    bench_config: dict | None = None,
    fail_fast: bool = False,
    progress_every: int = 50,
) -> dict[str, Any]:
    cases: list[tuple[BenchCase, str]] = []
    label_counts: dict[str, dict[str, int]] = {}
    for suite in suites:
        label_counts[suite.name] = {label: 0 for label in suite.labels}
        for case in suite.cases:
            label_counts[suite.name][case.label] += 1
            cases.append((case, suite.endpoint))

    workers = resolve_workers(workers, len(cases), bench_config or {})

    results: list[CaseResult] = []
    started = time.perf_counter()
    print(f"Running {len(cases)} cases with {workers} workers against {gateway_url}", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map: dict[Future[CaseResult], BenchCase] = {
            executor.submit(_classify_case, gateway_url, case, endpoint): case
            for case, endpoint in cases
        }
        pending = set(future_map.keys())
        completed = 0
        while pending:
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                result = future.result()
                results.append(result)
                completed += 1
                if not result.ok and fail_fast:
                    for other in pending:
                        other.cancel()
                    pending.clear()
                    break
                if completed % progress_every == 0 or completed == len(cases):
                    elapsed = time.perf_counter() - started
                    rate = completed / elapsed if elapsed > 0 else 0.0
                    passed = sum(1 for r in results if r.ok)
                    print(f"  {completed}/{len(cases)} ({rate:.1f}/s, {passed} passed)", flush=True)

    elapsed = time.perf_counter() - started
    return build_report(
        gateway_url=gateway_url,
        workers=workers,
        label_counts=label_counts,
        results=results,
        elapsed_sec=elapsed,
    )
