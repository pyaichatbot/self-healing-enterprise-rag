from __future__ import annotations

from dataclasses import dataclass

from shrag.settings import settings


@dataclass(slots=True)
class WebFallbackDecision:
    enabled: bool
    reason: str


@dataclass(slots=True)
class WebFallbackPolicy:
    enabled: bool
    min_chunks: int
    min_best_score: float
    reason_no_chunks: str
    reason_low_confidence: str
    reason_local_sufficient: str


def fallback_policy_from_settings() -> WebFallbackPolicy:
    return WebFallbackPolicy(
        enabled=settings.retrieval_web_fallback_enabled,
        min_chunks=settings.retrieval_web_fallback_min_chunks,
        min_best_score=settings.retrieval_web_fallback_min_best_score,
        reason_no_chunks=settings.retrieval_web_fallback_reason_no_chunks,
        reason_low_confidence=settings.retrieval_web_fallback_reason_low_confidence,
        reason_local_sufficient=settings.retrieval_web_fallback_reason_local_sufficient,
    )


def should_fallback_to_web(
    retrieved_count: int,
    best_score: float,
    policy: WebFallbackPolicy | None = None,
) -> WebFallbackDecision:
    active_policy = policy or fallback_policy_from_settings()
    if not active_policy.enabled:
        return WebFallbackDecision(enabled=False, reason=active_policy.reason_local_sufficient)
    if retrieved_count < active_policy.min_chunks:
        return WebFallbackDecision(enabled=True, reason=active_policy.reason_no_chunks)
    if best_score < active_policy.min_best_score:
        return WebFallbackDecision(enabled=True, reason=active_policy.reason_low_confidence)
    return WebFallbackDecision(enabled=False, reason=active_policy.reason_local_sufficient)
