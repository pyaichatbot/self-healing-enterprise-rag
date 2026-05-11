from shrag.grade.pipeline import NoOpGradeStage
from shrag.observe.models import RequestContext, RetrievedChunk


def test_noop_grade_preserves_input_order_and_ranking_metadata():
    context = RequestContext(request_id="r1", query="latest policy")
    chunks = (
        RetrievedChunk(chunk_id="c2", source_id="s1", text="B", score=0.82, rank=2),
        RetrievedChunk(chunk_id="c1", source_id="s1", text="A", score=0.95, rank=1),
    )

    result = NoOpGradeStage().grade(context, chunks)

    assert result.selected_chunks == chunks
    assert result.selected_chunks[0].rank == 2
    assert result.selected_chunks[1].score == 0.95
