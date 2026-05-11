from __future__ import annotations

from collections.abc import Sequence

from shrag.eval.stage_metrics import StageMetric, error_rate


def summarize_metrics(metrics: Sequence[StageMetric]) -> dict[str, float]:
    if not metrics:
        return {"error_rate": 0.0, "p95_latency_ms": 0.0}

    latencies = sorted(metric.latency_ms for metric in metrics)
    index = int(0.95 * (len(latencies) - 1))
    return {
        "error_rate": error_rate(list(metrics)),
        "p95_latency_ms": float(latencies[index]),
    }
