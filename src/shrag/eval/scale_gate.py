from __future__ import annotations

from dataclasses import dataclass

from shrag.observe.models import RequestContext


@dataclass(slots=True)
class ScaleGateDecision:
    allowed: bool
    reason: str = "not_configured"


class ScaleGate:
    """Deterministic capacity-aware eval gate for rollout safety."""

    def __init__(
        self,
        max_in_flight: int = 100,
        max_queue_lag_seconds: int = 120,
        max_error_rate: float = 0.02,
        min_retrieval_recall_at_k: float = 0.75,
    ) -> None:
        self.max_in_flight = max_in_flight
        self.max_queue_lag_seconds = max_queue_lag_seconds
        self.max_error_rate = max_error_rate
        self.min_retrieval_recall_at_k = min_retrieval_recall_at_k

    def allow(self, context: RequestContext) -> ScaleGateDecision:
        in_flight = int(context.metadata.get("in_flight", 0))
        if in_flight >= self.max_in_flight:
            return ScaleGateDecision(allowed=False, reason="capacity_exceeded")
        queue_lag_seconds = int(context.metadata.get("queue_lag_seconds", 0))
        if queue_lag_seconds > self.max_queue_lag_seconds:
            return ScaleGateDecision(allowed=False, reason="queue_lag_exceeded")
        error_rate = float(context.metadata.get("error_rate", 0.0))
        if error_rate > self.max_error_rate:
            return ScaleGateDecision(allowed=False, reason="error_rate_exceeded")
        retrieval_recall_at_k = float(context.metadata.get("retrieval_recall_at_k", 1.0))
        if retrieval_recall_at_k < self.min_retrieval_recall_at_k:
            return ScaleGateDecision(allowed=False, reason="retrieval_recall_below_target")
        return ScaleGateDecision(allowed=True, reason="within_capacity")
