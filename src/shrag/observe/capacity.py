from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class CapacityStatus:
    saturated: bool
    utilization: float


def capacity_gate(in_flight: int, max_in_flight: int) -> CapacityStatus:
    if max_in_flight <= 0:
        return CapacityStatus(saturated=True, utilization=1.0)
    utilization = in_flight / max_in_flight
    return CapacityStatus(saturated=utilization >= 1.0, utilization=min(utilization, 1.0))
