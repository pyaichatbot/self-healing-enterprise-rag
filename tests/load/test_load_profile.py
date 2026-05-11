from shrag.api.backpressure import InflightGuard


def test_inflight_guard_blocks_beyond_limit():
    guard = InflightGuard(max_inflight=2)
    assert guard.try_enter() is True
    assert guard.try_enter() is True
    assert guard.try_enter() is False
    guard.exit()
    assert guard.try_enter() is True
