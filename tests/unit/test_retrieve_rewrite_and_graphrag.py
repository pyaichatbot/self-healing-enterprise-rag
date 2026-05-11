from __future__ import annotations

import os

from shrag.retrieve import graphrag
from shrag.retrieve.graphrag import _rrf, graph_retrieve
from shrag.retrieve.rewrite import RewriteStrategy, _llm_complete, _resolve_strategy, rewrite_query


def test_rewrite_query_invalid_strategy_falls_back_to_synonym(monkeypatch):
    monkeypatch.setenv("SHRAG_REWRITE_STRATEGY", "unknown")
    out = rewrite_query("What is cloud vs edge?")
    assert out.strategy == "synonym"
    assert "comparison" in out.rewritten


def test_rewrite_query_decompose_uses_first_subquery(monkeypatch):
    monkeypatch.setattr("shrag.retrieve.rewrite._decompose", lambda query: ["first leg", "second leg"])
    out = rewrite_query("multi hop", strategy=RewriteStrategy.DECOMPOSE)
    assert out.rewritten == "first leg"
    assert out.sub_queries == ["first leg", "second leg"]


def test_rrf_fuses_ranked_lists_with_preference_for_repeated_ids():
    fused = _rrf(["a", "b", "c"], ["b", "d"], ["b", "a"])  # b appears in all lists
    assert fused[0][0] == "b"
    ids = [item[0] for item in fused]
    assert ids.index("a") < ids.index("c")


def test_graph_retrieve_hybrid_with_stubbed_channels(monkeypatch):
    monkeypatch.setattr(graphrag, "_sparse_retrieve", lambda query, top_k: [("s1", 1.0), ("s2", 0.5)])
    monkeypatch.setattr(graphrag, "_extract_entities", lambda text: ["Acme"])
    monkeypatch.setattr(graphrag, "_graph_expand", lambda entity, hops: ["g1", "g2"])
    monkeypatch.setattr(graphrag, "_load_chunk", lambda chunk_id: (f"text:{chunk_id}", f"src:{chunk_id}"))

    class _StubDense:
        def retrieve(self, context, top_k=5):
            class _R:
                chunks = (
                    type("C", (), {"chunk_id": "d1"})(),
                    type("C", (), {"chunk_id": "s1"})(),
                )

            return _R()

    monkeypatch.setattr("shrag.retrieve.pipeline.BaselineRetrievalStage", _StubDense)

    out = graph_retrieve("acme latest status", top_k=3, mode="hybrid")
    assert len(out) == 3
    assert all(item.chunk_id for item in out)
    assert any(item.retrieval_channel in {"hybrid", "dense", "sparse", "graph"} for item in out)


def test_graph_retrieve_sparse_mode_handles_load_miss(monkeypatch):
    monkeypatch.setattr(graphrag, "_sparse_retrieve", lambda query, top_k: [("missing", 1.0)])
    monkeypatch.setattr(graphrag, "_load_chunk", lambda chunk_id: (f"[chunk:{chunk_id}]", "unknown"))
    out = graph_retrieve("query", top_k=1, mode="sparse")

    assert len(out) == 1
    assert out[0].chunk_id == "missing"


def test_graph_retrieve_graph_mode_dedupes_graph_ids(monkeypatch):
    monkeypatch.setattr(graphrag, "_extract_entities", lambda text: ["Acme", "Acme"])
    monkeypatch.setattr(graphrag, "_graph_expand", lambda entity, hops: ["g1", "g1", "g2"])
    monkeypatch.setattr(graphrag, "_load_chunk", lambda chunk_id: (f"txt:{chunk_id}", f"src:{chunk_id}"))

    out = graph_retrieve("Acme merger", top_k=5, mode="graph", hops=3)

    ids = [chunk.chunk_id for chunk in out]
    assert ids == ["g1", "g2"]
    assert all(chunk.retrieval_channel in {"graph", "hybrid"} for chunk in out)


def test_graph_retrieve_dense_mode_handles_backend_failure(monkeypatch):
    class _BoomDense:
        def retrieve(self, context, top_k=5):
            raise RuntimeError("dense backend down")

    monkeypatch.setattr("shrag.retrieve.pipeline.BaselineRetrievalStage", _BoomDense)

    out = graph_retrieve("reliability test", top_k=3, mode="dense")

    assert out == []


def test_graph_expand_networkx_backend_fallback(monkeypatch):
    monkeypatch.setenv("SHRAG_GRAPH_BACKEND", "networkx")
    monkeypatch.setenv("SHRAG_GRAPH_PATH", "/path/does/not/exist.gpickle")

    out = graphrag._graph_expand("Acme", hops=2)
    assert out == []


def test_graph_expand_neo4j_backend_fallback(monkeypatch):
    monkeypatch.setenv("SHRAG_GRAPH_BACKEND", "neo4j")

    out = graphrag._graph_expand("Acme", hops=2)
    assert out == []


def test_load_chunk_not_found_returns_placeholder(tmp_path, monkeypatch):
    import sqlite3

    db_path = tmp_path / "missing.db"
    monkeypatch.setenv("SHRAG_STATE_DB_PATH", str(db_path))
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS chunks (chunk_id TEXT PRIMARY KEY, text TEXT, source_id TEXT)")
        conn.commit()

    text, source = graphrag._load_chunk("nope")

    assert text.startswith("[chunk not found:")
    assert source == "unknown"


def test_rewrite_none_and_normalize_strategies():
    none_out = rewrite_query("  hi!! ", strategy=RewriteStrategy.NONE)
    norm_out = rewrite_query("  hi!! ", strategy=RewriteStrategy.NORMALIZE)
    assert none_out.rewritten == "  hi!! "
    assert norm_out.rewritten == "hi"


def test_rewrite_hyde_fallback_and_step_back(monkeypatch):
    monkeypatch.setattr("shrag.retrieve.rewrite._llm_complete", lambda prompt, max_tokens=200: "")
    hyde = rewrite_query("what is rag", strategy=RewriteStrategy.HYDE)
    step = rewrite_query("what is rag", strategy=RewriteStrategy.STEP_BACK)
    assert hyde.rewritten == "what is rag"
    assert hyde.hyde_passage is None
    assert step.rewritten == "what is rag"


def test_resolve_strategy_defaults_to_synonym_on_invalid_env(monkeypatch):
    monkeypatch.setenv("SHRAG_REWRITE_STRATEGY", "bad")
    assert _resolve_strategy(None) == RewriteStrategy.SYNONYM


def test_llm_complete_returns_empty_for_mock_backend(monkeypatch):
    monkeypatch.setenv("SHRAG_LLM_BACKEND", "mock")
    assert _llm_complete("q") == ""


def test_llm_complete_openai_import_failure(monkeypatch):
    monkeypatch.setenv("SHRAG_LLM_BACKEND", "openai")
    monkeypatch.setitem(os.sys.modules, "openai", None)
    out = _llm_complete("q")
    assert out == ""
