from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class StageMetric:
    stage: str
    latency_ms: int
    success: bool


def error_rate(metrics: list[StageMetric]) -> float:
    if not metrics:
        return 0.0
    failures = sum(1 for metric in metrics if not metric.success)
    return failures / len(metrics)
