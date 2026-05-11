import time

from shrag.heal import canary


class _ImmediateThread:
    def __init__(self, target, daemon=True, name=None):
        self._target = target

    def start(self):
        self._target()


def test_canary_enabled_ratio_boundaries():
    assert canary.canary_enabled("req-a", ratio=0.0) is False
    assert canary.canary_enabled("req-a", ratio=1.0) is True


def test_run_canary_shadow_records_pass_and_stats(monkeypatch):
    canary._canary_results.clear()
    canary._error_window.clear()
    monkeypatch.setattr(canary.threading, "Thread", _ImmediateThread)

    canary.run_canary_shadow("r-canary-1", baseline_score=0.5, shadow_fn=lambda: 0.7, alert_threshold=-0.1)

    stats = canary.get_canary_stats(last_n=10)
    assert stats["count"] >= 1
    assert stats["passed"] >= 1


def test_run_canary_shadow_records_error_when_shadow_fn_raises(monkeypatch):
    canary._canary_results.clear()
    canary._error_window.clear()
    monkeypatch.setattr(canary.threading, "Thread", _ImmediateThread)

    def _boom():
        raise RuntimeError("shadow failure")

    canary.run_canary_shadow("r-canary-2", baseline_score=0.9, shadow_fn=_boom, alert_threshold=-0.1)

    stats = canary.get_canary_stats(last_n=10)
    assert stats["count"] >= 1
    assert stats["failed"] >= 1


def test_run_canary_shadow_returns_none_when_circuit_open(monkeypatch):
    canary._canary_results.clear()
    canary._error_window.clear()
    now = time.time()
    canary._error_window.extend([now] * 100)
    monkeypatch.setattr(canary, "_MAX_ERROR_RATE", 0.01)

    result = canary.run_canary_shadow("r-canary-3", baseline_score=0.5, shadow_fn=lambda: 0.5)

    assert result is None
