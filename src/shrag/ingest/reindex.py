from __future__ import annotations


def should_reindex(drift_score: float, threshold: float = 0.2) -> bool:
    return drift_score >= threshold
