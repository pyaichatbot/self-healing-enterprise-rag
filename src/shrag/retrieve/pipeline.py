from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Protocol, Sequence

from shrag.ingest.embed import embed_text
from shrag.ingest.store import get_store
from shrag.observe.models import RequestContext, RetrievedChunk
from shrag.retrieve.graphrag import graph_retrieve
from shrag.retrieve.hybrid import blend_scores
from shrag.retrieve.rerank import rerank_chunks
from shrag.retrieve.rewrite import rewrite_query
from shrag.retrieve.router import route_query
from shrag.retrieve.web_fallback import should_fallback_to_web
from shrag.settings import settings


@dataclass(slots=True)
class RetrieveResult:
    chunks: tuple[RetrievedChunk, ...] = ()


class RetrievalStage(Protocol):
    def retrieve(self, context: RequestContext, top_k: int = 5) -> RetrieveResult: ...


class BaselineRetrievalStage:
    """Deterministic baseline retrieval stage used for local end-to-end behavior."""

    def retrieve(self, context: RequestContext, top_k: int = 5) -> RetrieveResult:
        store = get_store()
        rewrite_result = rewrite_query(context.query)
        rewritten = rewrite_result.rewritten
        route = route_query(context)
        if settings.retrieval_graph_enabled and route.mode in {"graph", "hybrid", settings.retrieval_graph_mode}:
            graph_chunks = graph_retrieve(
                rewritten,
                top_k=top_k,
                mode=settings.retrieval_graph_mode,
                context=context,
            )
            as_chunks = tuple(
                RetrievedChunk(
                    chunk_id=g.chunk_id,
                    source_id=g.source_id,
                    text=g.text,
                    score=float(g.score),
                    rank=index + 1,
                    metadata={
                        **dict(g.metadata),
                        "route": "graph",
                        "route_reason": route.reason,
                        "retrieval_channel": g.retrieval_channel,
                    },
                )
                for index, g in enumerate(graph_chunks[:top_k])
            )
            return RetrieveResult(chunks=as_chunks)
        query_tokens = {token for token in rewritten.lower().split() if token}
        if not query_tokens:
            return RetrieveResult()

        tenant_id = str(context.metadata.get("tenant_id", "public"))
        corpus = [
            chunk
            for chunk in store.all()
            if chunk.metadata.get("tenant_id") in (tenant_id, "public", None)
        ]

        chunks: list[RetrievedChunk] = []
        query_vec: tuple[float, ...] | None = None
        if settings.retrieval_use_dense_embeddings:
            try:
                query_vec = embed_text(rewritten)
            except Exception:
                query_vec = None
        for base in corpus:
            chunk_tokens = set(base.text.lower().split())
            overlap = len(query_tokens & chunk_tokens)
            if overlap == 0:
                continue
            lexical = overlap / max(len(query_tokens), 1)
            dense = _dense_score(query_vec, base.metadata.get("_embedding"))
            semantic = (settings.retrieval_dense_weight * dense) + (settings.retrieval_sparse_weight * lexical)
            semantic = max(0.0, min(1.0, semantic))
            chunks.append(blend_scores(base, lexical_score=lexical, semantic_score=semantic))

        if not chunks and settings.retrieval_synthetic_fill_enabled:
            for index, token in enumerate(sorted(query_tokens)[: max(top_k * 2, 6)]):
                base = RetrievedChunk(
                    chunk_id=f"synthetic-{index + 1}",
                    source_id=f"synthetic:{token}",
                    text=f"Evidence snippet about {token} from {route.mode} retrieval.",
                    rank=index + 1,
                    metadata={"tenant_id": tenant_id, "route": route.mode, "route_reason": route.reason},
                )
                lexical = 1.0 / (index + 1)
                semantic = min(1.0, 0.45 + (len(token) / 20))
                chunks.append(blend_scores(base, lexical_score=lexical, semantic_score=semantic))

        reranked = rerank_chunks(chunks, rewritten)
        if settings.retrieval_dedupe_enabled:
            reranked = _dedupe_chunks(reranked)
        reranked = _cap_per_source(reranked, settings.retrieval_max_chunks_per_source)[:top_k]
        reranked = tuple(
            RetrievedChunk(
                chunk_id=chunk.chunk_id,
                source_id=chunk.source_id,
                text=chunk.text,
                score=chunk.score,
                rank=chunk.rank,
                metadata={**dict(chunk.metadata), "route": route.mode, "route_reason": route.reason},
            )
            for chunk in reranked
        )
        fallback = should_fallback_to_web(len(reranked), reranked[0].score if reranked else 0.0)
        if fallback.enabled:
            reranked = tuple(
                list(reranked)
                + [
                    RetrievedChunk(
                        chunk_id="web-fallback",
                        source_id="web:fallback",
                        text=f"Web fallback used due to {fallback.reason}.",
                        score=0.3,
                        rank=len(reranked) + 1,
                        metadata={
                            "tenant_id": "public",
                            "route": "web",
                            "route_reason": route.reason,
                            "fallback_reason": fallback.reason,
                        },
                    )
                ]
            )[:top_k]

        return RetrieveResult(chunks=tuple(reranked))


NoOpRetrievalStage = BaselineRetrievalStage


def _dedupe_chunks(chunks: Sequence[RetrievedChunk]) -> tuple[RetrievedChunk, ...]:
    seen: set[tuple[str, str]] = set()
    unique: list[RetrievedChunk] = []
    for chunk in chunks:
        key = (chunk.source_id, " ".join(chunk.text.lower().split()))
        if key in seen:
            continue
        seen.add(key)
        unique.append(chunk)
    return tuple(unique)


def _cap_per_source(chunks: Sequence[RetrievedChunk], max_per_source: int) -> tuple[RetrievedChunk, ...]:
    counts: dict[str, int] = {}
    capped: list[RetrievedChunk] = []
    for chunk in chunks:
        current = counts.get(chunk.source_id, 0)
        if current >= max_per_source:
            continue
        counts[chunk.source_id] = current + 1
        capped.append(chunk)
    return tuple(capped)


def _dense_score(query_vec: tuple[float, ...] | None, stored: object) -> float:
    if query_vec is None:
        return 0.0
    if not isinstance(stored, list) or not stored:
        return 0.0
    try:
        chunk_vec = [float(v) for v in stored]
    except Exception:
        return 0.0
    size = min(len(query_vec), len(chunk_vec))
    if size == 0:
        return 0.0
    dot = sum(query_vec[i] * chunk_vec[i] for i in range(size))
    q_norm = math.sqrt(sum(query_vec[i] * query_vec[i] for i in range(size)))
    c_norm = math.sqrt(sum(chunk_vec[i] * chunk_vec[i] for i in range(size)))
    if q_norm == 0 or c_norm == 0:
        return 0.0
    cosine = dot / (q_norm * c_norm)
    return max(0.0, min(1.0, (cosine + 1.0) / 2.0))
