from __future__ import annotations

from shrag.eval.active_sampler import canary_window_sample_rate, judge_window_sample_rate
from shrag.eval.enterprise_gates import (
    BucketContract,
    CanaryPolicy,
    CriticalErrorPolicy,
    FlakeControlPolicy,
    JudgeSamplingPolicy,
)
from shrag.eval.regression import RegressionGate


def test_bucket_contract_from_env_and_validate(monkeypatch):
    monkeypatch.setenv("SHRAG_EVAL_REQUIRED_BUCKET_TAGS", "risk_tier,domain,multi_hop")
    contract = BucketContract.from_env()

    ok = contract.validate({"risk_tier": "high", "domain": "legal", "multi_hop": "yes"})
    assert ok.allowed is True

    bad = contract.validate({"risk_tier": "high", "domain": "legal"})
    assert bad.allowed is False
    assert bad.reason == "missing_bucket_tags:multi_hop"


def test_critical_error_policy_enforces_protected_tier_zero_threshold(monkeypatch):
    monkeypatch.setenv("SHRAG_EVAL_CRITICAL_ERROR_THRESHOLDS", "pii_leakage:2,unsafe_instruction_compliance:1")
    monkeypatch.setenv("SHRAG_EVAL_STRICT_RISK_TIERS", "high,critical")
    monkeypatch.setenv("SHRAG_EVAL_PROTECTED_BUCKET_THRESHOLD", "0")

    policy = CriticalErrorPolicy.from_env()

    blocked = policy.evaluate({"pii_leakage": 1}, {"risk_tier": "critical"})
    assert blocked.allowed is False
    assert blocked.reason.startswith("critical_error:pii_leakage")

    allowed = policy.evaluate({"pii_leakage": 1}, {"risk_tier": "low"})
    assert allowed.allowed is True


def test_canary_policy_windows_and_rollback(monkeypatch):
    monkeypatch.setenv("SHRAG_EVAL_CANARY_MIN_SAMPLE_SIZE", "50")
    monkeypatch.setenv("SHRAG_EVAL_CANARY_REQUIRED_HEALTHY_WINDOWS", "2")
    monkeypatch.setenv("SHRAG_EVAL_CANARY_ROLLBACK_ERROR_RATE", "0.05")

    policy = CanaryPolicy.from_env()

    assert policy.can_promote(sample_size=49, healthy_windows=2).allowed is False
    assert policy.can_promote(sample_size=100, healthy_windows=2).allowed is True
    assert policy.should_rollback(error_rate=0.01, critical_error_count=1).allowed is False
    assert policy.should_rollback(error_rate=0.2, critical_error_count=0).allowed is False
    assert policy.should_rollback(error_rate=0.01, critical_error_count=0).allowed is True


def test_judge_sampling_policy(monkeypatch):
    monkeypatch.setenv("SHRAG_EVAL_JUDGE_MIN_SAMPLES", "80")
    monkeypatch.setenv("SHRAG_EVAL_JUDGE_MIN_AGREEMENT", "0.9")
    monkeypatch.setenv("SHRAG_EVAL_JUDGE_MAX_STABILITY_DELTA", "0.03")

    policy = JudgeSamplingPolicy.from_env()

    assert policy.evaluate_calibration(sample_count=50, agreement=0.95, stability_delta=0.01).allowed is False
    assert policy.evaluate_calibration(sample_count=100, agreement=0.85, stability_delta=0.01).allowed is False
    assert policy.evaluate_calibration(sample_count=100, agreement=0.95, stability_delta=0.05).allowed is False
    assert policy.evaluate_calibration(sample_count=100, agreement=0.95, stability_delta=0.02).allowed is True


def test_flake_control_policy(monkeypatch):
    monkeypatch.setenv("SHRAG_EVAL_FLAKE_MAX_REL_STDDEV", "0.05")
    monkeypatch.setenv("SHRAG_EVAL_FLAKE_MIN_QUALITY_MEDIAN", "0.8")

    policy = FlakeControlPolicy.from_env()

    low_quality = policy.evaluate([0.7, 0.79, 0.8])
    assert low_quality.allowed is False
    assert low_quality.reason == "median_quality_below_threshold"

    high_flake = policy.evaluate([0.8, 0.95, 0.6])
    assert high_flake.allowed is False
    assert high_flake.reason == "relative_stddev_exceeded"

    stable = policy.evaluate([0.82, 0.83, 0.84])
    assert stable.allowed is True


def test_regression_gate_from_env(monkeypatch):
    monkeypatch.setenv("SHRAG_EVAL_REGRESSION_MIN_QUALITY", "0.8")
    monkeypatch.setenv("SHRAG_EVAL_REGRESSION_MAX_ERROR_RATE", "0.1")

    gate = RegressionGate.from_env()
    assert gate.min_quality == 0.8
    assert gate.max_error_rate == 0.1
    assert gate.check(quality=0.79, error_rate_value=0.01) == (False, "quality_below_threshold")
    assert gate.check(quality=0.85, error_rate_value=0.2) == (False, "error_rate_above_threshold")
    assert gate.check(quality=0.85, error_rate_value=0.01) == (True, "pass")


def test_sampling_window_rates_from_env(monkeypatch):
    monkeypatch.setenv("SHRAG_EVAL_CANARY_SAMPLE_RATE", "0.15")
    monkeypatch.setenv("SHRAG_EVAL_JUDGE_SAMPLE_RATE", "0.35")

    assert canary_window_sample_rate() == 0.15
    assert judge_window_sample_rate() == 0.35
