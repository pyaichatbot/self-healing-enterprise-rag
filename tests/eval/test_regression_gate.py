from shrag.eval.pipeline_eval import EvalResult, merge_eval_results
from shrag.observe.models import ScoreArtifact


def _passes_regression_gate(result: EvalResult, threshold: float = 0.95) -> bool:
    if not result.scores:
        return False
    avg = sum(score.value for score in result.scores) / len(result.scores)
    return avg >= threshold


def test_merge_eval_results_and_block_on_regression_drop():
    baseline = EvalResult(scores=(ScoreArtifact(name="groundedness", value=0.99),))
    candidate = EvalResult(scores=(ScoreArtifact(name="groundedness", value=0.90),))

    merged = merge_eval_results((baseline, candidate))

    assert len(merged.scores) == 2
    assert _passes_regression_gate(merged, threshold=0.95) is False
