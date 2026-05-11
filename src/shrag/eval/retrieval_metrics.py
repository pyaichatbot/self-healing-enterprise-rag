from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(slots=True)
class RetrievalMetricResult:
    precision_at_k: float
    recall_at_k: float
    mrr: float
    ndcg_at_k: float


def compute_retrieval_metrics(
    retrieved_ids: Sequence[str],
    relevant_ids: Sequence[str],
    *,
    k: int = 5,
) -> RetrievalMetricResult:
    top = list(retrieved_ids[:k])
    rel = set(relevant_ids)
    if not top:
        return RetrievalMetricResult(precision_at_k=0.0, recall_at_k=0.0, mrr=0.0, ndcg_at_k=0.0)
    hits = [1 if doc_id in rel else 0 for doc_id in top]
    precision = sum(hits) / len(top)
    recall = sum(hits) / max(1, len(rel))

    reciprocal_rank = 0.0
    for i, doc_id in enumerate(top, start=1):
        if doc_id in rel:
            reciprocal_rank = 1.0 / i
            break

    dcg = 0.0
    for i, hit in enumerate(hits, start=1):
        if hit:
            dcg += 1.0 / _log2(i + 1)
    ideal_hits = min(len(rel), len(top))
    idcg = sum(1.0 / _log2(i + 1) for i in range(1, ideal_hits + 1))
    ndcg = dcg / idcg if idcg > 0 else 0.0

    return RetrievalMetricResult(
        precision_at_k=precision,
        recall_at_k=recall,
        mrr=reciprocal_rank,
        ndcg_at_k=ndcg,
    )


def _log2(value: float) -> float:
    import math

    return math.log(value, 2)

