from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class QueryScaleMetrics:
    p95_ms: float
    retrieval_p95_ms: float
    retrieval_recall_at_k: float


def query_latency_gate(
    metrics: QueryScaleMetrics,
    max_end_to_end_ms: float = 2500.0,
    max_retrieval_ms: float = 900.0,
    min_recall_at_k: float = 0.75,
) -> tuple[bool, str]:
    if metrics.p95_ms > max_end_to_end_ms:
        return False, "query_p95_above_target"
    if metrics.retrieval_p95_ms > max_retrieval_ms:
        return False, "retrieval_p95_above_target"
    if metrics.retrieval_recall_at_k < min_recall_at_k:
        return False, "retrieval_recall_below_target"
    return True, "pass"
