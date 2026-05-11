from shrag.heal import repair
from shrag.heal.repair import RepairStrategy, repair_response
from shrag.observe.models import GenerationResult, RequestContext, RetrievedChunk


def _ctx() -> RequestContext:
    return RequestContext(request_id="r1", query="q", user_id="u1", metadata={"tenant_id": "t1"})


def _gen() -> GenerationResult:
    return GenerationResult(response_text="base answer")


def test_repair_append_note_strategy_marks_fallback():
    result = repair_response(_gen(), "faithfulness_low", strategy=RepairStrategy.APPEND_NOTE)
    assert result.strategy == "append_note"
    assert result.succeeded is False
    assert "repair-note" in result.generation.response_text


def test_repair_strict_cite_fallback_without_context_or_chunks():
    result = repair_response(_gen(), "bad_citation", strategy=RepairStrategy.STRICT_CITE)
    assert result.strategy == "strict_cite_fallback"
    assert result.succeeded is False


def test_repair_hyde_rewrite_success_path(monkeypatch):
    monkeypatch.setattr(repair, "_build_hyde_query", lambda q: f"hyde:{q}")
    monkeypatch.setattr(
        repair,
        "_re_retrieve",
        lambda context, rewritten_query: (
            RetrievedChunk(chunk_id="c1", source_id="s1", text="evidence", score=0.9, rank=1),
        ),
    )
    monkeypatch.setattr(repair, "_strict_cite_generate", lambda context, chunks: "new answer with [1]")

    result = repair_response(_gen(), "quality_low", context=_ctx(), strategy=RepairStrategy.HYDE_REWRITE)

    assert result.strategy == "hyde_rewrite"
    assert result.succeeded is True
    assert "new answer" in result.generation.response_text


def test_repair_full_loop_exhausted_when_no_new_chunks(monkeypatch):
    monkeypatch.setattr(repair, "_build_hyde_query", lambda q: q)
    monkeypatch.setattr(repair, "_re_retrieve", lambda context, rewritten_query: ())

    result = repair_response(_gen(), "quality_low", context=_ctx(), strategy=RepairStrategy.FULL_LOOP)

    assert result.strategy == "exhausted"
    assert result.succeeded is False
    assert "could not find sufficient reliable information" in result.generation.response_text.lower()


def test_repair_no_reason_returns_success_noop():
    result = repair_response(_gen(), "", strategy=RepairStrategy.FULL_LOOP)
    assert result.succeeded is True
    assert result.rounds_used == 0


def test_repair_strict_cite_success():
    chunks = (RetrievedChunk(chunk_id="c1", source_id="s1", text="evidence", score=0.9, rank=1),)
    out = repair_response(_gen(), "bad cite", context=_ctx(), original_chunks=chunks, strategy=RepairStrategy.STRICT_CITE)
    assert out.succeeded is True
    assert out.strategy == "strict_cite"


def test_repair_invalid_strategy_string_defaults_full_loop(monkeypatch):
    monkeypatch.setattr(repair, "_build_hyde_query", lambda q: q)
    monkeypatch.setattr(repair, "_re_retrieve", lambda context, rewritten_query: ())
    out = repair_response(_gen(), "low", context=_ctx(), strategy="invalid")
    assert out.strategy == "exhausted"
