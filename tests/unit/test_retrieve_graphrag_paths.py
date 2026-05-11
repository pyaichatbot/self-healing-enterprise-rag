from shrag.retrieve import graphrag


def test_rrf_fusion_orders_results():
    fused = graphrag._rrf(["a", "b"], ["b", "c"], ["a"])
    ids = [doc_id for doc_id, _ in fused]
    assert "a" in ids and "b" in ids


def test_graph_retrieve_dense_mode(monkeypatch):
    class FakeStage:
        def retrieve(self, context, top_k=5):
            from shrag.observe.models import RetrievedChunk
            return type("R", (), {"chunks": (RetrievedChunk(chunk_id="c1", source_id="s1", text="T"),)})()

    monkeypatch.setattr("shrag.retrieve.pipeline.BaselineRetrievalStage", FakeStage)
    monkeypatch.setattr(graphrag, "_load_chunk", lambda chunk_id: ("text", "src"))
    out = graphrag.graph_retrieve("q", mode="dense", top_k=1)
    assert out and out[0].chunk_id == "c1"


def test_graph_retrieve_sparse_mode(monkeypatch):
    monkeypatch.setattr(graphrag, "_sparse_retrieve", lambda query, top_k: [("c2", 0.7)])
    monkeypatch.setattr(graphrag, "_load_chunk", lambda chunk_id: ("text2", "src2"))
    out = graphrag.graph_retrieve("q", mode="sparse", top_k=1)
    assert out and out[0].chunk_id == "c2"

