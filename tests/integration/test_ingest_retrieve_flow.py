from shrag.ingest.pipeline import BaselineIngestStage, IngestDocument
from shrag.observe.models import RequestContext
from shrag.retrieve.pipeline import BaselineRetrievalStage


def test_ingest_then_retrieve_returns_relevant_chunks():
    ingest = BaselineIngestStage()
    retrieve = BaselineRetrievalStage()

    context_ingest = RequestContext(
        request_id="ing-1",
        query="ingest",
        user_id="u1",
        metadata={"tenant_id": "tenant-a"},
    )
    ingest.ingest(
        context_ingest,
        (
            IngestDocument(document_id="doc-1", text="FastAPI production deployment runbook and rollback plan."),
            IngestDocument(document_id="doc-2", text="Qdrant vector index design and retrieval quality metrics."),
        ),
    )

    context_query = RequestContext(
        request_id="q-1",
        query="rollback plan",
        user_id="u1",
        metadata={"tenant_id": "tenant-a"},
    )
    result = retrieve.retrieve(context_query, top_k=3)
    assert result.chunks
    assert any("rollback" in chunk.text.lower() for chunk in result.chunks)
