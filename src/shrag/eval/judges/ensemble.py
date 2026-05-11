from __future__ import annotations

from dataclasses import dataclass
from statistics import mean

from shrag.observe.models import GenerationResult, RequestContext


@dataclass(slots=True)
class EnsembleVerdict:
    mean_score: float
    disagreement: bool
    scores: tuple[float, ...]


class BaselineMultiJudgeEnsemble:
    """Deterministic multi-judge baseline used for quality-gate hardening."""

    def evaluate(self, context: RequestContext, generation: GenerationResult) -> EnsembleVerdict:
        text = generation.response_text or ""
        # Three deterministic "judges" to emulate diversified scoring.
        coverage_judge = min(1.0, len(text) / 320.0)
        citation_judge = 1.0 if generation.citations else 0.35
        user_alignment_judge = 1.0 if (context.query.lower() in text.lower() or len(text) > 60) else 0.45
        scores = (coverage_judge, citation_judge, user_alignment_judge)
        score_mean = float(mean(scores))
        disagreement = (max(scores) - min(scores)) >= 0.4
        return EnsembleVerdict(mean_score=score_mean, disagreement=disagreement, scores=scores)
