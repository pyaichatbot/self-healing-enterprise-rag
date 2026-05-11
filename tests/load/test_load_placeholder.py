from shrag.api.backpressure import InflightGuard


def test_load_guard_recovers_after_release():
    guard = InflightGuard(max_inflight=1)
    assert guard.try_enter() is True
    assert guard.try_enter() is False
    guard.exit()
    assert guard.try_enter() is True
