from shrag.heal.circuit import circuit_breaker_from_policy, load_circuit_policy
from shrag.heal.retry import RetryPolicy, load_retry_policy, run_with_retry


def test_retry_policy_yaml_loads():
    policy = load_retry_policy()
    assert policy.max_attempts >= 2
    assert policy.backoff_seconds > 0


def test_run_with_retry_recovers_after_transient_failure():
    calls = {"count": 0}

    def flaky():
        calls["count"] += 1
        if calls["count"] < 2:
            raise RuntimeError("transient")
        return "ok"

    result = run_with_retry(flaky, RetryPolicy(max_attempts=3, backoff_seconds=0.0, jitter=False))
    assert result == "ok"
    assert calls["count"] == 2


def test_circuit_policy_yaml_loads_and_applies():
    policy = load_circuit_policy()
    assert policy["error_rate_threshold"] > 0
    decision = circuit_breaker_from_policy(error_rate=1.0)
    assert decision.open is True
