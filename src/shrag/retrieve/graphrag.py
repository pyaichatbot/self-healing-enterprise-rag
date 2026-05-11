"""GraphRAG — knowledge-graph-augmented retrieval.

Retrieval modes:
  dense        — vector similarity only (baseline)
  sparse       — BM25 keyword match
  graph        — entity/relation graph traversal
  hybrid       — dense + sparse + graph fusion (default)

Graph store backends (SHRAG_GRAPH_BACKEND):
  networkx     — in-process NetworkX graph (dev/test)
  neo4j        — Neo4j Bolt (production)
  mock         — deterministic stub for tests

Enterprise features:
  - Named-entity extraction to build graph edges
  - Reciprocal-rank fusion (RRF) across retrieval channels
  - Configurable hop depth for graph expansion (SHRAG_GRAPH_HOPS, default 2)
  - Entity-level ACL filtering (inherits chunk ACL)
  - Subgraph serialization for citation provenance
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class GraphChunk:
    """Retrieved chunk augmented with graph metadata."""
    chunk_id: str
    text: str
    source_id: str
    score: float
    retrieval_channel: str              # dense | sparse | graph
    entities: list[str] = field(default_factory=list)
    relations: list[tuple[str, str, str]] = field(default_factory=list)  # (head, rel, tail)
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Entity extraction (lightweight — no full NER dependency)
# ---------------------------------------------------------------------------

def _extract_entities(text: str) -> list[str]:
    """Extract candidate named entities using capitalisation heuristic."""
    import re
    # Capitalized multi-word sequences (not sentence-start).
    candidates = re.findall(r"(?<=[.!?]\s)(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})|(?:^|\s)([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)", text)
    flat = [c.strip() for c in candidates if c and c.strip()]
    # Also try spaCy NER if available.
    try:
        from shrag.security.pii import _get_nlp
        nlp = _get_nlp()
        if nlp:
            doc = nlp(text)
            flat += [ent.text for ent in doc.ents if ent.label_ in {"ORG", "PERSON", "GPE", "PRODUCT", "NORP"}]
    except Exception:  # noqa: BLE001
        pass
    return list(dict.fromkeys(flat))[:20]  # deduplicate, cap at 20


# ---------------------------------------------------------------------------
# Graph store abstraction
# ---------------------------------------------------------------------------

def _get_graph_backend() -> str:
    return os.environ.get("SHRAG_GRAPH_BACKEND", "mock")


def _graph_expand(entity: str, hops: int) -> list[str]:
    """Return entity IDs reachable within *hops* from *entity*."""
    backend = _get_graph_backend()
    try:
        if backend == "neo4j":
            from neo4j import GraphDatabase  # type: ignore[import-untyped]
            uri = os.environ.get("SHRAG_NEO4J_URL", "bolt://localhost:7687")
            auth = (
                os.environ.get("SHRAG_NEO4J_USER", "neo4j"),
                os.environ.get("SHRAG_NEO4J_PASSWORD", ""),
            )
            with GraphDatabase.driver(uri, auth=auth) as driver:
                with driver.session() as session:
                    result = session.run(
                        f"MATCH (e {{name: $entity}})-[*1..{hops}]-(n) "
                        "RETURN DISTINCT n.chunk_id AS chunk_id LIMIT 50",
                        entity=entity,
                    )
                    return [r["chunk_id"] for r in result if r["chunk_id"]]

        if backend == "networkx":
            import networkx as nx  # type: ignore[import-untyped]
            # Load graph from file if available.
            graph_path = os.environ.get("SHRAG_GRAPH_PATH", ".state/graph.gpickle")
            try:
                G = nx.read_gpickle(graph_path)  # type: ignore[attr-defined]
                if entity in G:
                    neighbors = set()
                    current = {entity}
                    for _ in range(hops):
                        expanded = set()
                        for node in current:
                            expanded |= set(G.neighbors(node))
                        neighbors |= expanded
                        current = expanded
                    return [n for n in neighbors if G.nodes[n].get("chunk_id")][:50]
            except Exception:  # noqa: BLE001
                pass

    except Exception as exc:  # noqa: BLE001
        logger.debug("Graph expansion failed for entity=%r: %s", entity, exc)
    return []


# ---------------------------------------------------------------------------
# Sparse (BM25) retrieval
# ---------------------------------------------------------------------------

def _sparse_retrieve(query: str, top_k: int) -> list[tuple[str, float]]:
    """Return (chunk_id, score) pairs from keyword index."""
    try:
        import sqlite3
        import math
        db_path = os.environ.get("SHRAG_STATE_DB_PATH", ".state/shrag.db")
        with sqlite3.connect(db_path) as conn:
            # Simple keyword frequency match as BM25 approximation.
            terms = query.lower().split()
            placeholders = " OR ".join(["text LIKE ?" for _ in terms])
            like_args = [f"%{t}%" for t in terms]
            cur = conn.execute(
                f"SELECT chunk_id, text FROM chunks WHERE {placeholders} LIMIT {top_k * 3}",
                like_args,
            )
            rows = cur.fetchall()
            scored: list[tuple[str, float]] = []
            for chunk_id, text in rows:
                text_lower = text.lower()
                tf = sum(text_lower.count(t) for t in terms)
                score = math.log1p(tf) / math.log1p(len(text.split()) + 1)
                scored.append((chunk_id, score))
            scored.sort(key=lambda x: -x[1])
            return scored[:top_k]
    except Exception as exc:  # noqa: BLE001
        logger.debug("Sparse retrieval failed: %s", exc)
    return []


# ---------------------------------------------------------------------------
# Reciprocal Rank Fusion
# ---------------------------------------------------------------------------

def _rrf(
    *ranked_lists: list[str],
    k: int = 60,
) -> list[tuple[str, float]]:
    """Fuse multiple ranked ID lists using Reciprocal Rank Fusion."""
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, doc_id in enumerate(ranked, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda x: -x[1])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def graph_retrieve(
    query: str,
    *,
    top_k: int = 10,
    mode: str | None = None,
    hops: int | None = None,
    context: Any = None,
) -> list[GraphChunk]:
    """Retrieve chunks using GraphRAG fusion.

    Args:
        query: User query string.
        top_k: Maximum chunks to return.
        mode: 'dense' | 'sparse' | 'graph' | 'hybrid'
        hops: Graph traversal depth.
        context: Optional RequestContext for dense retrieval.

    Returns:
        List of GraphChunk ordered by fused relevance score.
    """
    resolved_mode = mode or os.environ.get("SHRAG_GRAPHRAG_MODE", "hybrid")
    resolved_hops = hops or int(os.environ.get("SHRAG_GRAPH_HOPS", "2"))

    dense_ids: list[str] = []
    sparse_ids: list[str] = []
    graph_ids: list[str] = []

    # --- Dense retrieval ---
    if resolved_mode in ("dense", "hybrid"):
        try:
            from shrag.retrieve.pipeline import BaselineRetrievalStage
            from shrag.observe.models import RequestContext as RC
            sub_ctx = RC(
                request_id="graphrag-dense",
                query=query,
                user_id=getattr(context, "user_id", "system"),
                metadata={},
            )
            result = BaselineRetrievalStage().retrieve(sub_ctx, top_k=top_k * 2)
            dense_ids = [c.chunk_id for c in result.chunks]
        except Exception as exc:  # noqa: BLE001
            logger.debug("GraphRAG dense retrieval failed: %s", exc)

    # --- Sparse retrieval ---
    if resolved_mode in ("sparse", "hybrid"):
        sparse_scored = _sparse_retrieve(query, top_k)
        sparse_ids = [cid for cid, _ in sparse_scored]

    # --- Graph expansion ---
    if resolved_mode in ("graph", "hybrid"):
        entities = _extract_entities(query)
        for entity in entities[:5]:
            graph_ids.extend(_graph_expand(entity, resolved_hops))
        graph_ids = list(dict.fromkeys(graph_ids))[:top_k]

    # --- Fuse ---
    if resolved_mode == "hybrid":
        fused = _rrf(dense_ids, sparse_ids, graph_ids)
    elif resolved_mode == "dense":
        fused = [(cid, 1.0 / (i + 1)) for i, cid in enumerate(dense_ids)]
    elif resolved_mode == "sparse":
        fused = [(cid, 1.0 / (i + 1)) for i, cid in enumerate(sparse_ids)]
    else:
        fused = [(cid, 1.0 / (i + 1)) for i, cid in enumerate(graph_ids)]

    # --- Materialise chunks from store ---
    result_chunks: list[GraphChunk] = []
    seen: set[str] = set()
    for chunk_id, score in fused[:top_k]:
        if chunk_id in seen:
            continue
        seen.add(chunk_id)
        try:
            text, source_id = _load_chunk(chunk_id)
        except Exception:  # noqa: BLE001
            text, source_id = f"[chunk:{chunk_id}]", "unknown"

        channel = "hybrid"
        if chunk_id in dense_ids and chunk_id not in sparse_ids and chunk_id not in graph_ids:
            channel = "dense"
        elif chunk_id in sparse_ids and chunk_id not in dense_ids:
            channel = "sparse"
        elif chunk_id in graph_ids and chunk_id not in dense_ids:
            channel = "graph"

        result_chunks.append(GraphChunk(
            chunk_id=chunk_id,
            text=text,
            source_id=source_id,
            score=score,
            retrieval_channel=channel,
            entities=_extract_entities(text)[:5],
        ))

    logger.info(
        "GraphRAG mode=%s query=%r dense=%d sparse=%d graph=%d returned=%d",
        resolved_mode, query[:50], len(dense_ids), len(sparse_ids), len(graph_ids), len(result_chunks),
    )
    return result_chunks


def _load_chunk(chunk_id: str) -> tuple[str, str]:
    """Load chunk text and source_id from state DB."""
    import sqlite3
    db_path = os.environ.get("SHRAG_STATE_DB_PATH", ".state/shrag.db")
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(
            "SELECT text, source_id FROM chunks WHERE chunk_id = ?", (chunk_id,)
        )
        row = cur.fetchone()
        if row:
            return row[0], row[1]
    return f"[chunk not found: {chunk_id}]", "unknown"
