"""Canary evaluation — shadow prompt testing for regression detection.

Canary mechanism:
  1. Sample a fraction of live requests (configurable ratio)
  2. Re-run the full pipeline with a shadow/canary prompt variant
  3. Compare canary output quality vs baseline
  4. Emit metrics; alert if canary scores degrade below threshold

Use cases:
  - Detect prompt regressions before full rollout
  - A/B test prompt variants in production traffic
  - Validate repair-loop changes on real queries

Enterprise features:
  - Stable hash-based sampling (same request_id always same bucket)
  - Async shadow execution (does not block main request path)
  - Per-canary-variant score tracking
  - Configurable alert threshold (SHRAG_CANARY_ALERT_THRESHOLD)
  - Circuit breaker: disable canary if error rate exceeds limit
"""
from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stable hash sampling
# ---------------------------------------------------------------------------

def canary_enabled(request_id: str, ratio: float | None = None) -> bool:
    """Return True for the fraction of requests that should run canary.

    Uses SHA-256 for uniform, stable distribution (same ID always same result).
    """
    resolved_ratio = ratio if ratio is not None else float(
        os.environ.get("SHRAG_CANARY_RATIO", "0.1")
    )
    digest = hashlib.sha256(request_id.encode()).hexdigest()
    # First 4 hex chars = 16-bit bucket (0–65535).
    bucket = int(digest[:4], 16) / 65535.0
    return bucket < resolved_ratio


# ---------------------------------------------------------------------------
# Canary result
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class CanaryResult:
    request_id: str
    variant: str
    baseline_score: float
    canary_score: float
    delta: float                         # canary_score - baseline_score
    passed: bool
    latency_seconds: float = 0.0
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Shadow execution
# ---------------------------------------------------------------------------

_canary_results: list[CanaryResult] = []
_canary_lock = threading.Lock()
_error_window: list[float] = []         # timestamps of recent errors
_WINDOW_SECONDS = 60.0
_MAX_ERROR_RATE = float(os.environ.get("SHRAG_CANARY_MAX_ERROR_RATE", "0.5"))


def _record_canary(result: CanaryResult) -> None:
    with _canary_lock:
        _canary_results.append(result)
        if len(_canary_results) > 1000:
            _canary_results.pop(0)
        if result.error:
            _error_window.append(time.time())
            # Prune old errors.
            cutoff = time.time() - _WINDOW_SECONDS
            _error_window[:] = [t for t in _error_window if t > cutoff]


def _circuit_open() -> bool:
    """Return True if canary error rate exceeds threshold."""
    with _canary_lock:
        cutoff = time.time() - _WINDOW_SECONDS
        recent_errors = sum(1 for t in _error_window if t > cutoff)
    # Rate = errors / window capacity (approximate).
    rate = recent_errors / max(1, int(_WINDOW_SECONDS / 10))
    return rate > _MAX_ERROR_RATE


def run_canary_shadow(
    request_id: str,
    baseline_score: float,
    shadow_fn: Callable[[], float],
    *,
    variant: str = "default",
    alert_threshold: float | None = None,
) -> CanaryResult | None:
    """Run shadow evaluation asynchronously.

    Args:
        request_id: Original request identifier.
        baseline_score: Quality score of the main pipeline response.
        shadow_fn: Callable that returns canary quality score (float).
        variant: Canary variant name for tracking.
        alert_threshold: Minimum acceptable canary score delta.

    Returns:
        CanaryResult or None if canary is disabled/circuit open.
    """
    if _circuit_open():
        logger.warning("Canary circuit open — skipping shadow eval for %s", request_id)
        return None

    threshold = alert_threshold if alert_threshold is not None else float(
        os.environ.get("SHRAG_CANARY_ALERT_THRESHOLD", "-0.1")
    )

    def _run() -> None:
        start = time.perf_counter()
        error = ""
        canary_score = 0.0
        try:
            canary_score = shadow_fn()
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
            logger.warning("Canary shadow failed for %s: %s", request_id, exc)

        elapsed = time.perf_counter() - start
        delta = canary_score - baseline_score
        passed = (delta >= threshold) and not error

        result = CanaryResult(
            request_id=request_id,
            variant=variant,
            baseline_score=baseline_score,
            canary_score=canary_score,
            delta=delta,
            passed=passed,
            latency_seconds=elapsed,
            error=error,
        )
        _record_canary(result)

        if not passed and not error:
            logger.warning(
                "Canary regression: variant=%s delta=%.3f threshold=%.3f request=%s",
                variant, delta, threshold, request_id,
            )
        else:
            logger.debug(
                "Canary passed: variant=%s delta=%.3f request=%s", variant, delta, request_id,
            )

        # Emit metric.
        try:
            from shrag.observe.metrics import set_quality_score
            set_quality_score(f"canary_{variant}", canary_score)
        except Exception:  # noqa: BLE001
            pass

    t = threading.Thread(target=_run, daemon=True, name=f"canary-{request_id[:8]}")
    t.start()
    return None  # Non-blocking; result recorded asynchronously.


def get_canary_stats(last_n: int = 100) -> dict[str, Any]:
    """Return summary statistics from recent canary evaluations."""
    with _canary_lock:
        recent = list(_canary_results[-last_n:])
    if not recent:
        return {"count": 0}
    passed = sum(1 for r in recent if r.passed)
    avg_delta = sum(r.delta for r in recent) / len(recent)
    return {
        "count": len(recent),
        "passed": passed,
        "failed": len(recent) - passed,
        "pass_rate": passed / len(recent),
        "avg_delta": round(avg_delta, 4),
        "circuit_open": _circuit_open(),
    }
