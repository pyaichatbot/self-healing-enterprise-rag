from __future__ import annotations

from collections.abc import Sequence

from shrag.observe.models import ScoreArtifact


def should_abstain(scores: Sequence[ScoreArtifact], min_score: float = 0.35) -> tuple[bool, str]:
    if not scores:
        return True, "no_scores"
    low = [score for score in scores if score.value < min_score]
    if low:
        return True, f"low_scores:{','.join(score.name for score in low)}"
    return False, "confident"
