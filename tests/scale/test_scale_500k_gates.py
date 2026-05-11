from tests.scale.failure_chaos import ChaosRecoveryMetrics, failure_chaos_gate
from tests.scale.ingest_500k import IngestScaleMetrics, ingest_capacity_gate
from tests.scale.query_500k import QueryScaleMetrics, query_latency_gate


def test_scale_ingest_gate():
    ok, reason = ingest_capacity_gate(IngestScaleMetrics(docs_per_hour=55_000, error_rate=0.004, queue_lag_p95_seconds=90.0))
    assert ok is True and reason == "pass"


def test_scale_query_gate():
    ok, reason = query_latency_gate(QueryScaleMetrics(p95_ms=2100.0, retrieval_p95_ms=700.0, retrieval_recall_at_k=0.82))
    assert ok is True and reason == "pass"


def test_scale_failure_chaos_gate():
    ok, reason = failure_chaos_gate(
        ChaosRecoveryMetrics(
            recovered=True,
            observed_recovery_seconds=900,
            rollback_invoked=True,
            data_loss_events=0,
        ),
        max_recovery_seconds=1800,
    )
    assert ok is True and reason == "pass"
