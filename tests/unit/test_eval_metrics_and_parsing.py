from __future__ import annotations

from shrag.eval.enterprise_gates import CriticalErrorPolicy, FlakeControlPolicy
from shrag.eval.metrics_runner import summarize_metrics
from shrag.eval.stage_metrics import StageMetric, error_rate


def test_stage_metrics_error_rate_and_summary():
    metrics = [
        StageMetric(stage="retrieve", latency_ms=20, success=True),
        StageMetric(stage="generate", latency_ms=60, success=False),
        StageMetric(stage="reflect", latency_ms=40, success=True),
    ]
    assert round(error_rate(metrics), 4) == round(1 / 3, 4)

    summary = summarize_metrics(metrics)
    assert summary["error_rate"] > 0
    assert summary["p95_latency_ms"] == 40.0


def test_critical_error_policy_ignores_malformed_threshold_tokens(monkeypatch):
    monkeypatch.setenv("SHRAG_EVAL_CRITICAL_ERROR_THRESHOLDS", "badtoken,pii_leakage:1")
    policy = CriticalErrorPolicy.from_env()

    assert policy.class_thresholds.get("pii_leakage") == 1
    # unknown class defaults to 0 threshold
    blocked = policy.evaluate({"unknown": 1}, {"risk_tier": "high"})
    assert blocked.allowed is False


def test_flake_policy_no_scores_blocked(monkeypatch):
    monkeypatch.setenv("SHRAG_EVAL_FLAKE_MIN_QUALITY_MEDIAN", "0.8")
    policy = FlakeControlPolicy.from_env()
    decision = policy.evaluate([])
    assert decision.allowed is False
    assert decision.reason == "no_scores"
