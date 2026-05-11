from __future__ import annotations

from shrag.observe.models import RetrievedChunk


def blend_scores(chunk: RetrievedChunk, lexical_score: float, semantic_score: float) -> RetrievedChunk:
    """Simple weighted blend used by hybrid retrieval baseline."""

    score = 0.4 * lexical_score + 0.6 * semantic_score
    return RetrievedChunk(
        chunk_id=chunk.chunk_id,
        source_id=chunk.source_id,
        text=chunk.text,
        score=score,
        rank=chunk.rank,
        metadata=dict(chunk.metadata),
    )
