from __future__ import annotations

from collections.abc import Sequence

from shrag.observe.models import ScoreArtifact


def calibrated_confidence(scores: Sequence[ScoreArtifact]) -> float:
    if not scores:
        return 0.0
    return max(0.0, min(1.0, sum(score.value for score in scores) / len(scores)))
