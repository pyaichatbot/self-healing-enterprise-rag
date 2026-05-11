from __future__ import annotations

from collections.abc import Sequence

from shrag.observe.models import RetrievedChunk, ScoreArtifact


def relevance_score(query: str, chunks: Sequence[RetrievedChunk]) -> float:
    query_tokens = set(query.lower().split())
    if not query_tokens or not chunks:
        return 0.0

    best = 0.0
    for chunk in chunks:
        chunk_tokens = set(chunk.text.lower().split())
        overlap = len(query_tokens.intersection(chunk_tokens))
        score = overlap / len(query_tokens)
        best = max(best, score)
    return best


def score_relevance(query: str, chunks: Sequence[RetrievedChunk]) -> tuple[ScoreArtifact, ...]:
    value = relevance_score(query, chunks)
    return (ScoreArtifact(name="relevance", value=value, passed=value >= 0.35),)
