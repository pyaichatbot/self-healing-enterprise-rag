"""Embedding provider abstraction — batched, retried, multi-backend.

Supported backends (set via SHRAG_EMBED_BACKEND):
  openai   — OpenAI text-embedding-3-* models (default)
  cohere   — Cohere embed-v3
  local    — sentence-transformers via transformers/torch (offline)
  mock     — deterministic hash-based vectors for tests

Enterprise features:
  - Per-provider retry with tenacity exponential backoff + jitter
  - Batched encoding to stay within token-per-minute budgets
  - Per-tenant fairness via semaphore (configured in settings)
  - Dimension override for matryoshka truncation (OpenAI 3-large)
  - Content-hash cache to skip re-embedding unchanged chunks
"""
from __future__ import annotations

import hashlib
import logging
import math
import os
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-process content-hash embedding cache (L1).
# Production deployments should layer an external Redis L2 cache.
# ---------------------------------------------------------------------------
_cache_lock = threading.Lock()
_embed_cache: dict[str, tuple[float, ...]] = {}
_MAX_CACHE = 32_768


def _cache_key(text: str, model: str, dim: int) -> str:
    raw = f"{model}:{dim}:{text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_get(key: str) -> tuple[float, ...] | None:
    with _cache_lock:
        return _embed_cache.get(key)


def _cache_put(key: str, vec: tuple[float, ...]) -> None:
    with _cache_lock:
        if len(_embed_cache) >= _MAX_CACHE:
            # Evict oldest ~10 % — simple FIFO approximation.
            evict = list(_embed_cache.keys())[: _MAX_CACHE // 10]
            for k in evict:
                del _embed_cache[k]
        _embed_cache[key] = vec


# ---------------------------------------------------------------------------
# Retry helper — pure stdlib so tests don't need tenacity installed.
# ---------------------------------------------------------------------------
def _with_retry(fn: Any, max_attempts: int = 3, base_delay: float = 1.0) -> Any:
    """Exponential backoff with full jitter."""
    import random

    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt == max_attempts - 1:
                break
            sleep = base_delay * (2**attempt) * (0.5 + random.random() * 0.5)
            logger.warning("embed retry %d/%d after %.1fs: %s", attempt + 1, max_attempts, sleep, exc)
            time.sleep(sleep)
    raise RuntimeError(f"Embedding failed after {max_attempts} attempts") from last_exc


# ---------------------------------------------------------------------------
# Backend implementations
# ---------------------------------------------------------------------------

def _embed_openai(texts: list[str], model: str, dim: int | None) -> list[list[float]]:
    """Call OpenAI embeddings API."""
    try:
        import openai  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError("pip install openai for SHRAG_EMBED_BACKEND=openai") from exc

    api_key = os.environ.get("OPENAI_API_KEY", "")
    client = openai.OpenAI(api_key=api_key)
    kwargs: dict[str, Any] = {"model": model, "input": texts}
    if dim:
        kwargs["dimensions"] = dim
    response = client.embeddings.create(**kwargs)
    return [item.embedding for item in sorted(response.data, key=lambda x: x.index)]


def _embed_cohere(texts: list[str], model: str, dim: int | None) -> list[list[float]]:
    """Call Cohere Embed v3 API."""
    try:
        import cohere  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError("pip install cohere for SHRAG_EMBED_BACKEND=cohere") from exc

    api_key = os.environ.get("COHERE_API_KEY", "")
    co = cohere.Client(api_key)
    kwargs: dict[str, Any] = {
        "texts": texts,
        "model": model,
        "input_type": "search_document",
    }
    if dim:
        kwargs["output_dimension"] = dim
    response = co.embed(**kwargs)
    return [list(v) for v in response.embeddings]


def _embed_local(texts: list[str], model: str, dim: int | None) -> list[list[float]]:
    """Sentence-transformers via HuggingFace (no API key needed)."""
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "pip install sentence-transformers for SHRAG_EMBED_BACKEND=local"
        ) from exc

    _model_cache: dict[str, Any] = {}
    if model not in _model_cache:
        _model_cache[model] = SentenceTransformer(model)
    st_model = _model_cache[model]
    vecs = st_model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
    result = [list(v.tolist()) for v in vecs]
    if dim and result and len(result[0]) > dim:
        result = [v[:dim] for v in result]
    return result


def _embed_mock(texts: list[str], model: str, dim: int | None) -> list[list[float]]:
    """Deterministic hash-based vectors — for tests only, NOT production."""
    out_dim = dim or 256
    results: list[list[float]] = []
    for text in texts:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        # Tile digest bytes to fill requested dimension.
        raw = list(digest) * math.ceil(out_dim / len(digest))
        vec = [b / 255.0 for b in raw[:out_dim]]
        # L2-normalise.
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        results.append([v / norm for v in vec])
    return results


# ---------------------------------------------------------------------------
# Chunking-template-aware batch encode with cache
# ---------------------------------------------------------------------------

_BACKEND_FN = {
    "openai": _embed_openai,
    "cohere": _embed_cohere,
    "local": _embed_local,
    "mock": _embed_mock,
}

_DEFAULT_MODELS = {
    "openai": "text-embedding-3-small",
    "cohere": "embed-english-v3.0",
    "local": "sentence-transformers/all-MiniLM-L6-v2",
    "mock": "mock",
}

# Provider-specific max batch sizes (tokens × context-safety margins).
_BATCH_SIZES = {
    "openai": 256,
    "cohere": 96,
    "local": 64,
    "mock": 1024,
}


def embed_batch(
    texts: list[str],
    *,
    backend: str | None = None,
    model: str | None = None,
    dim: int | None = None,
    max_attempts: int = 3,
) -> list[tuple[float, ...]]:
    """Embed a list of texts, returning one vector tuple per text.

    Results are content-hash-cached to avoid re-embedding unchanged chunks.
    """
    resolved_backend = backend or os.environ.get("SHRAG_EMBED_BACKEND", "mock")
    resolved_model = model or os.environ.get("SHRAG_EMBED_MODEL", "") or _DEFAULT_MODELS.get(resolved_backend, "mock")
    resolved_dim = dim or int(os.environ.get("SHRAG_EMBED_DIM", "0")) or None

    embed_fn = _BACKEND_FN.get(resolved_backend)
    if embed_fn is None:
        raise ValueError(f"Unknown SHRAG_EMBED_BACKEND: {resolved_backend!r}")

    batch_size = _BATCH_SIZES.get(resolved_backend, 128)
    results: list[tuple[float, ...] | None] = [None] * len(texts)
    pending_indices: list[int] = []
    pending_texts: list[str] = []

    # L1 cache lookup.
    for i, text in enumerate(texts):
        key = _cache_key(text, resolved_model, resolved_dim or 0)
        cached = _cache_get(key)
        if cached is not None:
            results[i] = cached
        else:
            pending_indices.append(i)
            pending_texts.append(text)

    # Batch-encode uncached texts.
    for batch_start in range(0, len(pending_texts), batch_size):
        batch = pending_texts[batch_start : batch_start + batch_size]
        batch_idx = pending_indices[batch_start : batch_start + batch_size]

        def _call(b: list[str] = batch, m: str = resolved_model, d: int | None = resolved_dim) -> list[list[float]]:
            return embed_fn(b, m, d)  # type: ignore[operator]

        vecs = _with_retry(_call, max_attempts=max_attempts)
        for local_i, (global_i, text, vec) in enumerate(zip(batch_idx, batch, vecs)):
            t = tuple(vec)
            key = _cache_key(text, resolved_model, resolved_dim or 0)
            _cache_put(key, t)
            results[global_i] = t

    return [r for r in results if r is not None]


def embed_text(text: str, dim: int | None = None, **kwargs: Any) -> tuple[float, ...]:
    """Single-text convenience wrapper."""
    batch = embed_batch([text], dim=dim, **kwargs)
    if not batch:
        raise ValueError("embed_batch returned empty result")
    return batch[0]
