from shrag.eval.pipeline_eval import BaselineEvalHook
from shrag.observe.models import GenerationResult, RequestContext


def _ctx(query: str) -> RequestContext:
    return RequestContext(request_id="req-1", query=query, user_id="u1", metadata={"tenant_id": "t1"})


def test_eval_hook_emits_judge_ensemble_score():
    hook = BaselineEvalHook()
    generation = GenerationResult(response_text="question answer with citation", citations=("doc-1",), scores=())
    result = hook.evaluate(_ctx("question"), generation)
    names = {score.name for score in result.scores}
    assert "judge_ensemble_score" in names


def test_eval_hook_flags_disagreement_for_weak_generation():
    hook = BaselineEvalHook()
    generation = GenerationResult(response_text="tiny", citations=(), scores=())
    result = hook.evaluate(_ctx("unrelated query"), generation)
    ensemble = [score for score in result.scores if score.name == "judge_ensemble_score"][0]
    assert ensemble.passed is False
    assert ensemble.reason == "ensemble_disagreement"
