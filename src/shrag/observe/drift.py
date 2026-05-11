from __future__ import annotations

from collections.abc import Sequence


def drift_score(baseline: Sequence[float], current: Sequence[float]) -> float:
    if not baseline or not current:
        return 0.0
    baseline_mean = sum(baseline) / len(baseline)
    current_mean = sum(current) / len(current)
    if baseline_mean == 0:
        return abs(current_mean)
    return abs(current_mean - baseline_mean) / abs(baseline_mean)
