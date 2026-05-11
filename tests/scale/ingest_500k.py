from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class IngestScaleMetrics:
    docs_per_hour: int
    error_rate: float
    queue_lag_p95_seconds: float


def ingest_capacity_gate(
    metrics: IngestScaleMetrics,
    min_docs_per_hour: int = 50_000,
    max_error_rate: float = 0.01,
    max_queue_lag_p95_seconds: float = 120.0,
) -> tuple[bool, str]:
    if metrics.docs_per_hour < min_docs_per_hour:
        return False, "ingest_throughput_below_target"
    if metrics.error_rate > max_error_rate:
        return False, "ingest_error_rate_above_target"
    if metrics.queue_lag_p95_seconds > max_queue_lag_p95_seconds:
        return False, "queue_lag_above_target"
    return True, "pass"
