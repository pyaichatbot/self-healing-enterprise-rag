from shrag.api import routes
from shrag.eval.pipeline_eval import EvalResult
from shrag.observe.models import GenerationResult, RequestContext, RetrievedChunk, ScoreArtifact


class _StubEvalHook:
    def evaluate(self, context: RequestContext, generation: GenerationResult) -> EvalResult:
        _ = context
        score = min(1.0, max(0.0, len(generation.response_text) / 100.0))
        return EvalResult(scores=(ScoreArtifact(name="quality", value=score),), notes=("ok",))


def _ctx() -> RequestContext:
    return RequestContext(
        request_id="r1",
        query="what is rag",
        user_id="u1",
        trace_id="t1",
        metadata={"tenant_id": "tenant-1"},
    )


def test_oracle_eval_mode_both_emits_two_lanes(monkeypatch):
    monkeypatch.setattr(routes, "_eval_hook", _StubEvalHook())
    monkeypatch.setattr(routes.settings, "eval_oracle_context_enabled", True)
    monkeypatch.setattr(routes.settings, "eval_oracle_context_mode", "both")
    monkeypatch.setattr(routes.settings, "eval_oracle_context_max_chars", 200)

    generation = GenerationResult(response_text="generated answer", citations=("s1",))
    chunks = (
        RetrievedChunk(chunk_id="c1", source_id="s1", text="retrieved evidence one", score=0.9, rank=1),
    )

    result = routes._evaluate_with_oracle_context(_ctx(), generation, chunks)

    names = {s.name for s in result.scores}
    assert "generation:quality" in names
    assert "oracle_retrieval:quality" in names


def test_oracle_eval_mode_retrieval_only(monkeypatch):
    monkeypatch.setattr(routes, "_eval_hook", _StubEvalHook())
    monkeypatch.setattr(routes.settings, "eval_oracle_context_enabled", True)
    monkeypatch.setattr(routes.settings, "eval_oracle_context_mode", "retrieval")

    generation = GenerationResult(response_text="generated answer", citations=())
    chunks = (RetrievedChunk(chunk_id="c1", source_id="s1", text="retrieved evidence", score=0.9, rank=1),)

    result = routes._evaluate_with_oracle_context(_ctx(), generation, chunks)

    names = {s.name for s in result.scores}
    assert "oracle_retrieval:quality" in names
    assert "generation:quality" not in names
