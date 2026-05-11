from __future__ import annotations

from collections.abc import Sequence

from shrag.observe.models import RetrievedChunk


def rerank_chunks(chunks: Sequence[RetrievedChunk], query: str) -> tuple[RetrievedChunk, ...]:
    tokens = set(query.lower().split())

    scored: list[RetrievedChunk] = []
    for chunk in chunks:
        overlap = len(tokens.intersection(chunk.text.lower().split()))
        combined = chunk.score + overlap * 0.1
        scored.append(
            RetrievedChunk(
                chunk_id=chunk.chunk_id,
                source_id=chunk.source_id,
                text=chunk.text,
                score=combined,
                rank=chunk.rank,
                metadata=dict(chunk.metadata),
            )
        )

    scored.sort(key=lambda c: c.score, reverse=True)
    return tuple(
        RetrievedChunk(
            chunk_id=chunk.chunk_id,
            source_id=chunk.source_id,
            text=chunk.text,
            score=chunk.score,
            rank=index + 1,
            metadata=chunk.metadata,
        )
        for index, chunk in enumerate(scored)
    )
