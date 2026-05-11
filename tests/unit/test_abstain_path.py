from shrag.generate.pipeline import NoOpGenerateStage
from shrag.observe.models import RequestContext
from shrag.retrieve.pipeline import NoOpRetrievalStage


def _abstain_if_no_context(context: RequestContext) -> tuple[bool, str]:
    retrieved = NoOpRetrievalStage().retrieve(context, top_k=5)
    if not retrieved.chunks:
        return True, "Insufficient evidence to answer confidently"
    generation = NoOpGenerateStage().generate(context, retrieved.chunks)
    return False, generation.response_text


def test_abstain_when_retrieval_returns_no_chunks():
    abstained, message = _abstain_if_no_context(RequestContext(request_id="r2", query="   "))

    assert abstained is True
    assert "Insufficient evidence" in message
