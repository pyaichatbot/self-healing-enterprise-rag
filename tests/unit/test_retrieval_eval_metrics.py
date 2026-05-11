from __future__ import annotations

from shrag.eval.retrieval_metrics import compute_retrieval_metrics


def test_retrieval_metrics_basic():
    result = compute_retrieval_metrics(
        retrieved_ids=["a", "b", "c", "d"],
        relevant_ids=["b", "d"],
        k=3,
    )
    assert round(result.precision_at_k, 4) == round(1 / 3, 4)
    assert round(result.recall_at_k, 4) == 0.5
    assert round(result.mrr, 4) == 0.5
    assert 0.0 <= result.ndcg_at_k <= 1.0


def test_retrieval_metrics_empty_inputs():
    result = compute_retrieval_metrics(retrieved_ids=[], relevant_ids=["x"], k=5)
    assert result.precision_at_k == 0.0
    assert result.recall_at_k == 0.0
    assert result.mrr == 0.0
    assert result.ndcg_at_k == 0.0


def test_retrieval_metrics_perfect_ordering():
    result = compute_retrieval_metrics(retrieved_ids=["r1", "r2", "r3"], relevant_ids=["r1", "r2"], k=2)
    assert result.precision_at_k == 1.0
    assert result.recall_at_k == 1.0
    assert result.mrr == 1.0
    assert result.ndcg_at_k == 1.0
