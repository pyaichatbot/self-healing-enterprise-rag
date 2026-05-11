from __future__ import annotations

from shrag.observe import metrics


def test_metrics_helpers_and_generation():
    metrics._metrics.clear()  # type: ignore[attr-defined]
    metrics._registry = None  # type: ignore[attr-defined]

    metrics.inc_request("retrieve", "ok", 2)
    metrics.observe_latency("retrieve", 0.02)
    metrics.inc_token_cost("mock", 123)
    metrics.set_quality_score("faithfulness", 0.8)
    metrics.inc_embed_cache_hit(True)
    metrics.inc_embed_cache_hit(False)

    payload = metrics.generate_latest()
    assert isinstance(payload, (bytes, bytearray))


def test_timed_context_records_error_path():
    metrics._metrics.clear()  # type: ignore[attr-defined]
    metrics._registry = None  # type: ignore[attr-defined]

    try:
        with metrics.timed("generate"):
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    payload = metrics.generate_latest()
    assert isinstance(payload, (bytes, bytearray))
