from shrag.retrieve.hybrid import blend_scores
from shrag.retrieve.pipeline import NoOpRetrievalStage, RetrievalStage, RetrieveResult
from shrag.retrieve.rerank import rerank_chunks
from shrag.retrieve.rewrite import rewrite_query
from shrag.retrieve.router import RetrievalRoute, RetrievalRoutingPolicy, route_query, routing_policy_from_settings
from shrag.retrieve.web_fallback import (
    WebFallbackDecision,
    WebFallbackPolicy,
    fallback_policy_from_settings,
    should_fallback_to_web,
)

__all__ = [
    "RetrieveResult",
    "RetrievalStage",
    "NoOpRetrievalStage",
    "RetrievalRoute",
    "RetrievalRoutingPolicy",
    "route_query",
    "routing_policy_from_settings",
    "rewrite_query",
    "blend_scores",
    "rerank_chunks",
    "WebFallbackDecision",
    "WebFallbackPolicy",
    "fallback_policy_from_settings",
    "should_fallback_to_web",
]
