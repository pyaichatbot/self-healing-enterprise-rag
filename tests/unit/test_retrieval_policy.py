from shrag.ingest.store import get_store
from shrag.observe.models import RequestContext
from shrag.observe.models import RetrievedChunk
from shrag.retrieve.pipeline import BaselineRetrievalStage
from shrag.retrieve.router import route_query
from shrag.retrieve.web_fallback import should_fallback_to_web
from shrag.settings import settings


def test_default_route_mode_is_used_when_query_shape_routing_disabled():
    settings.retrieval_default_mode = "hybrid"
    settings.retrieval_query_shape_routing_enabled = False
    settings.retrieval_reason_default = "env_default"

    route = route_query(RequestContext(request_id="r1", query="latest updates"))

    assert route.mode == "hybrid"
    assert route.reason == "env_default"


def test_query_shape_routing_applies_only_when_enabled():
    settings.retrieval_query_shape_routing_enabled = True
    settings.retrieval_time_sensitive_keywords = "latest,news"
    settings.retrieval_time_sensitive_mode = "hybrid"
    settings.retrieval_short_query_mode = "dense"
    settings.retrieval_long_query_mode = "sparse"
    settings.retrieval_short_query_max_terms = 2
    settings.retrieval_reason_time_sensitive = "ts"
    settings.retrieval_reason_short_query = "sq"
    settings.retrieval_reason_long_query = "lq"

    time_sensitive = route_query(RequestContext(request_id="r2", query="latest security patch"))
    short_query = route_query(RequestContext(request_id="r3", query="cache tuning"))
    long_query = route_query(RequestContext(request_id="r4", query="how do we optimize retrieval latency"))

    assert time_sensitive.mode == "hybrid"
    assert time_sensitive.reason == "ts"
    assert short_query.mode == "dense"
    assert short_query.reason == "sq"
    assert long_query.mode == "sparse"
    assert long_query.reason == "lq"


def test_fallback_policy_obeys_env_toggles_and_reasons():
    settings.retrieval_web_fallback_enabled = True
    settings.retrieval_web_fallback_min_chunks = 2
    settings.retrieval_web_fallback_min_best_score = 0.7
    settings.retrieval_web_fallback_reason_no_chunks = "empty"
    settings.retrieval_web_fallback_reason_low_confidence = "weak"
    settings.retrieval_web_fallback_reason_local_sufficient = "ok"

    assert should_fallback_to_web(retrieved_count=0, best_score=0.9).reason == "empty"
    assert should_fallback_to_web(retrieved_count=2, best_score=0.6).reason == "weak"
    assert should_fallback_to_web(retrieved_count=2, best_score=0.9).reason == "ok"

    settings.retrieval_web_fallback_enabled = False
    disabled = should_fallback_to_web(retrieved_count=0, best_score=0.0)
    assert disabled.enabled is False
    assert disabled.reason == "ok"


def test_retrieval_stage_exposes_active_route_reason_in_metadata():
    settings.retrieval_default_mode = "hybrid"
    settings.retrieval_reason_default = "default_hybrid"
    settings.retrieval_query_shape_routing_enabled = False
    settings.retrieval_web_fallback_enabled = False

    store = get_store()
    store.upsert(
        RetrievedChunk(
            chunk_id="rpol-1",
            source_id="policy-doc",
            text="Alpha beta retrieval policy document.",
            metadata={"tenant_id": "tenant-a"},
        )
    )

    context = RequestContext(request_id="r5", query="alpha beta", metadata={"tenant_id": "tenant-a"})
    result = BaselineRetrievalStage().retrieve(context, top_k=1)

    assert result.chunks
    assert result.chunks[0].metadata.get("route") == "hybrid"
    assert result.chunks[0].metadata.get("route_reason") == "default_hybrid"
