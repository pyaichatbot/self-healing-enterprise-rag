from __future__ import annotations

from dataclasses import dataclass

from shrag.observe.models import RequestContext
from shrag.settings import settings


@dataclass(slots=True)
class RetrievalRoute:
    mode: str
    reason: str


@dataclass(slots=True)
class RetrievalRoutingPolicy:
    default_mode: str
    query_shape_routing_enabled: bool
    time_sensitive_keywords: tuple[str, ...]
    short_query_max_terms: int
    time_sensitive_mode: str
    short_query_mode: str
    long_query_mode: str
    default_reason: str
    time_sensitive_reason: str
    short_query_reason: str
    long_query_reason: str


def routing_policy_from_settings() -> RetrievalRoutingPolicy:
    keywords = tuple(
        token.strip().lower()
        for token in settings.retrieval_time_sensitive_keywords.split(",")
        if token.strip()
    )
    return RetrievalRoutingPolicy(
        default_mode=settings.retrieval_default_mode,
        query_shape_routing_enabled=settings.retrieval_query_shape_routing_enabled,
        time_sensitive_keywords=keywords,
        short_query_max_terms=settings.retrieval_short_query_max_terms,
        time_sensitive_mode=settings.retrieval_time_sensitive_mode,
        short_query_mode=settings.retrieval_short_query_mode,
        long_query_mode=settings.retrieval_long_query_mode,
        default_reason=settings.retrieval_reason_default,
        time_sensitive_reason=settings.retrieval_reason_time_sensitive,
        short_query_reason=settings.retrieval_reason_short_query,
        long_query_reason=settings.retrieval_reason_long_query,
    )


def route_query(context: RequestContext, policy: RetrievalRoutingPolicy | None = None) -> RetrievalRoute:
    active_policy = policy or routing_policy_from_settings()
    if not active_policy.query_shape_routing_enabled:
        return RetrievalRoute(mode=active_policy.default_mode, reason=active_policy.default_reason)

    query = context.query.lower()
    if any(token in query for token in active_policy.time_sensitive_keywords):
        return RetrievalRoute(mode=active_policy.time_sensitive_mode, reason=active_policy.time_sensitive_reason)
    if len(query.split()) <= active_policy.short_query_max_terms:
        return RetrievalRoute(mode=active_policy.short_query_mode, reason=active_policy.short_query_reason)
    return RetrievalRoute(mode=active_policy.long_query_mode, reason=active_policy.long_query_reason)
