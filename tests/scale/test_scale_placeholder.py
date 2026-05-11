from tests.scale.ingest_500k import IngestScaleMetrics, ingest_capacity_gate


def test_scale_gate_rejects_high_queue_lag():
    ok, reason = ingest_capacity_gate(
        IngestScaleMetrics(
            docs_per_hour=52_000,
            error_rate=0.001,
            queue_lag_p95_seconds=300.0,
        )
    )
    assert ok is False
    assert reason == "queue_lag_above_target"
