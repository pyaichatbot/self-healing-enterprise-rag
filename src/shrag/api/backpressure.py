from __future__ import annotations

from threading import Lock
from contextlib import contextmanager
from collections.abc import Iterator


class InflightGuard:
    """Simple in-memory inflight request guard."""

    def __init__(self, max_inflight: int) -> None:
        self._max_inflight = max_inflight
        self._inflight = 0
        self._lock = Lock()

    def try_enter(self) -> bool:
        with self._lock:
            if self._inflight >= self._max_inflight:
                return False
            self._inflight += 1
            return True

    def exit(self) -> None:
        with self._lock:
            if self._inflight > 0:
                self._inflight -= 1

    @property
    def inflight(self) -> int:
        return self._inflight


# TODO: replace with adaptive backpressure tied to latency and queue depth.


class StageBulkhead:
    """Fixed-capacity stage guard to isolate expensive pipeline steps."""

    def __init__(self, stage: str, max_inflight: int) -> None:
        self.stage = stage
        self._guard = InflightGuard(max_inflight)

    @contextmanager
    def enter(self) -> Iterator[None]:
        if not self._guard.try_enter():
            raise RuntimeError(f"Stage bulkhead saturated: {self.stage}")
        try:
            yield
        finally:
            self._guard.exit()

    @property
    def inflight(self) -> int:
        return self._guard.inflight
