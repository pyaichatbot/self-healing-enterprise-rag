from shrag.eval.scale_gate import ScaleGate
from shrag.observe.models import RequestContext


def _ctx(**metadata):
    return RequestContext(request_id="r1", query="q", user_id="u", metadata=metadata)


def test_scale_gate_blocks_when_queue_lag_exceeds_threshold():
    gate = ScaleGate(max_in_flight=100, max_queue_lag_seconds=120)
    decision = gate.allow(_ctx(in_flight=1, queue_lag_seconds=240))
    assert decision.allowed is False
    assert decision.reason == "queue_lag_exceeded"


def test_scale_gate_blocks_when_error_rate_exceeds_threshold():
    gate = ScaleGate(max_error_rate=0.02)
    decision = gate.allow(_ctx(in_flight=1, queue_lag_seconds=10, error_rate=0.2))
    assert decision.allowed is False
    assert decision.reason == "error_rate_exceeded"


def test_scale_gate_blocks_when_recall_drops():
    gate = ScaleGate(min_retrieval_recall_at_k=0.8)
    decision = gate.allow(_ctx(in_flight=1, queue_lag_seconds=10, error_rate=0.0, retrieval_recall_at_k=0.5))
    assert decision.allowed is False
    assert decision.reason == "retrieval_recall_below_target"
