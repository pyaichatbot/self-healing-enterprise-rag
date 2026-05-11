from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from shrag.grade.crag import score_crag
from shrag.grade.faithfulness import score_faithfulness
from shrag.grade.relevance import score_relevance
from shrag.observe.models import RequestContext, RetrievedChunk, ScoreArtifact


@dataclass(slots=True)
class GradeResult:
    chunk_scores: tuple[ScoreArtifact, ...] = ()
    selected_chunks: tuple[RetrievedChunk, ...] = ()


class GradeStage(Protocol):
    def grade(self, context: RequestContext, chunks: Sequence[RetrievedChunk]) -> GradeResult: ...


class BaselineGradeStage:
    """Deterministic baseline grader using CRAG/relevance/faithfulness heuristics."""

    def grade(self, context: RequestContext, chunks: Sequence[RetrievedChunk]) -> GradeResult:
        selected = tuple(chunks[:5])
        crag_scores = score_crag(selected)
        relevance_scores = score_relevance(context.query, selected)
        faith_scores = score_faithfulness(context.query, selected)
        all_scores: tuple[ScoreArtifact, ...] = tuple(crag_scores + relevance_scores + faith_scores)
        threshold = 0.35
        filtered = tuple(chunk for chunk in selected if chunk.score >= threshold)
        return GradeResult(chunk_scores=all_scores, selected_chunks=filtered)


NoOpGradeStage = BaselineGradeStage
