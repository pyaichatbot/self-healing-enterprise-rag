from __future__ import annotations

from collections.abc import Sequence

from shrag.observe.models import RetrievedChunk, ScoreArtifact


def faithfulness_score(answer: str, chunks: Sequence[RetrievedChunk]) -> float:
    if not answer.strip() or not chunks:
        return 0.0
    corpus = " ".join(chunk.text.lower() for chunk in chunks)
    answer_tokens = {token for token in answer.lower().split() if len(token) > 3}
    if not answer_tokens:
        return 0.0
    supported = sum(1 for token in answer_tokens if token in corpus)
    return supported / len(answer_tokens)


def score_faithfulness(query: str, chunks: Sequence[RetrievedChunk]) -> tuple[ScoreArtifact, ...]:
    value = faithfulness_score(query, chunks)
    return (ScoreArtifact(name="faithfulness", value=value, passed=value >= 0.4),)
