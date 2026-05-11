from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from shrag.eval.judges.ensemble import BaselineMultiJudgeEnsemble
from shrag.eval.regression import RegressionGate
from shrag.observe.models import GenerationResult, RequestContext, ScoreArtifact


@dataclass(slots=True)
class EvalResult:
    scores: tuple[ScoreArtifact, ...] = ()
    notes: tuple[str, ...] = ()


class EvalHook(Protocol):
    def evaluate(self, context: RequestContext, generation: GenerationResult) -> EvalResult: ...


class BaselineEvalHook:
    def __init__(self) -> None:
        self._ensemble = BaselineMultiJudgeEnsemble()

    def evaluate(self, context: RequestContext, generation: GenerationResult) -> EvalResult:
        verdict = self._ensemble.evaluate(context, generation)
        quality = min(1.0, max(0.0, len(generation.response_text) / 300.0))
        error_rate = 0.0 if generation.response_text else 1.0
        passed, reason = RegressionGate().check(quality=max(quality, verdict.mean_score), error_rate_value=error_rate)
        if verdict.disagreement:
            passed = False
            reason = "judge_ensemble_disagreement"
        return EvalResult(
            scores=(
                ScoreArtifact(name="quality", value=quality, passed=passed, reason=reason),
                ScoreArtifact(name="error_rate", value=error_rate, passed=passed, reason=reason),
                ScoreArtifact(
                    name="judge_ensemble_score",
                    value=verdict.mean_score,
                    passed=not verdict.disagreement,
                    reason="ensemble_consensus" if not verdict.disagreement else "ensemble_disagreement",
                ),
            ),
            notes=(
                reason,
                f"user={context.user_id or 'anonymous'}",
                f"judge_scores={','.join(f'{s:.3f}' for s in verdict.scores)}",
            ),
        )


NoOpEvalHook = BaselineEvalHook


def merge_eval_results(results: Sequence[EvalResult]) -> EvalResult:
    """Combine eval outputs from multiple hooks."""

    scores: list[ScoreArtifact] = []
    notes: list[str] = []
    for result in results:
        scores.extend(result.scores)
        notes.extend(result.notes)
    return EvalResult(scores=tuple(scores), notes=tuple(notes))
