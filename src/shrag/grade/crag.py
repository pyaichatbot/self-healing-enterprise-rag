from __future__ import annotations

from collections.abc import Sequence

from shrag.observe.models import RetrievedChunk, ScoreArtifact


def score_crag(chunks: Sequence[RetrievedChunk]) -> tuple[ScoreArtifact, ...]:
    """Context reliability score derived from rank-weighted retrieval scores."""

    if not chunks:
        return (ScoreArtifact(name="crag", value=0.0, reason="empty_context", passed=False),)

    total_weight = 0.0
    weighted = 0.0
    for chunk in chunks:
        weight = 1.0 / max(chunk.rank, 1)
        total_weight += weight
        weighted += weight * max(chunk.score, 0.0)
    value = weighted / total_weight if total_weight else 0.0
    return (ScoreArtifact(name="crag", value=value, passed=value >= 0.45),)
