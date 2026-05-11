"""LLM keyword extraction with Redis-backed cache.

Extracts domain-relevant keywords from each chunk for:
  - Sparse retrieval (BM25 / keyword index boost)
  - Faceted search filters
  - Tag-based ACL routing

Backends:
  - LLM extraction (openai/anthropic/ollama/mock via SHRAG_LLM_BACKEND)
  - YAKE fallback (pure-python, no API key needed)
  - Simple TF heuristic as final fallback

Cache:
  - Content-hash keyed
  - Redis (L2) if SHRAG_REDIS_URL configured, else in-process dict (L1)
  - TTL: SHRAG_KEYWORD_CACHE_TTL seconds (default 86400)

Enterprise features:
  - Configurable max keywords per chunk (SHRAG_KEYWORD_MAX, default 10)
  - Domain stopword filter (SHRAG_KEYWORD_STOPWORDS comma-separated)
  - Batch extraction for ingest pipelines
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# In-process L1 cache
# ---------------------------------------------------------------------------

_cache_lock = threading.Lock()
_cache: dict[str, list[str]] = {}
_MAX_CACHE = 16_384


def _cache_key(text: str, max_keywords: int) -> str:
    raw = f"kw:{max_keywords}:{text}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _l1_get(key: str) -> list[str] | None:
    with _cache_lock:
        return _cache.get(key)


def _l1_put(key: str, keywords: list[str]) -> None:
    with _cache_lock:
        if len(_cache) >= _MAX_CACHE:
            evict = list(_cache.keys())[: _MAX_CACHE // 10]
            for k in evict:
                del _cache[k]
        _cache[key] = keywords


# ---------------------------------------------------------------------------
# Redis L2 cache
# ---------------------------------------------------------------------------

def _redis_get(key: str) -> list[str] | None:
    redis_url = os.environ.get("SHRAG_REDIS_URL")
    if not redis_url:
        return None
    try:
        import redis  # type: ignore[import-untyped]
        r = redis.from_url(redis_url)
        raw = r.get(f"shrag:kw:{key}")
        if raw:
            return json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Redis keyword cache get failed: %s", exc)
    return None


def _redis_put(key: str, keywords: list[str]) -> None:
    redis_url = os.environ.get("SHRAG_REDIS_URL")
    if not redis_url:
        return
    ttl = int(os.environ.get("SHRAG_KEYWORD_CACHE_TTL", "86400"))
    try:
        import redis  # type: ignore[import-untyped]
        r = redis.from_url(redis_url)
        r.setex(f"shrag:kw:{key}", ttl, json.dumps(keywords))
    except Exception as exc:  # noqa: BLE001
        logger.debug("Redis keyword cache put failed: %s", exc)


# ---------------------------------------------------------------------------
# Stopword filter
# ---------------------------------------------------------------------------

_BASE_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "this", "that", "these", "those", "it", "its", "as", "so", "if", "not",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "then", "than", "also", "more",
}


def _stopwords() -> set[str]:
    extra = os.environ.get("SHRAG_KEYWORD_STOPWORDS", "")
    custom = {w.strip().lower() for w in extra.split(",") if w.strip()}
    return _BASE_STOPWORDS | custom


# ---------------------------------------------------------------------------
# Extraction backends
# ---------------------------------------------------------------------------

_LLM_PROMPT = (
    "Extract up to {n} key technical terms, concepts, or named entities from "
    "the following text. Return only the keywords as a comma-separated list, "
    "no explanations.\n\nText:\n{text}\n\nKeywords:"
)


def _extract_llm(text: str, max_keywords: int) -> list[str]:
    try:
        from shrag.generate.llm import complete
        prompt = _LLM_PROMPT.format(n=max_keywords, text=text[:1500])
        raw = complete(prompt, max_tokens=max_keywords * 8, temperature=0.0)
        parts = re.split(r"[,\n;]+", raw)
        kws = [p.strip().lower() for p in parts if 2 < len(p.strip()) < 60]
        stops = _stopwords()
        return [k for k in kws if k not in stops][:max_keywords]
    except Exception as exc:  # noqa: BLE001
        logger.debug("LLM keyword extraction failed: %s", exc)
    return []


def _extract_yake(text: str, max_keywords: int) -> list[str]:
    try:
        import yake  # type: ignore[import-untyped]
        extractor = yake.KeywordExtractor(lan="en", n=3, top=max_keywords)
        results = extractor.extract_keywords(text)
        stops = _stopwords()
        return [kw.lower() for kw, _score in results if kw.lower() not in stops][:max_keywords]
    except Exception:  # noqa: BLE001
        pass
    return []


def _extract_tfidf_heuristic(text: str, max_keywords: int) -> list[str]:
    """Simple TF heuristic — last-resort fallback."""
    words = re.findall(r"\b[a-zA-Z][a-zA-Z\-]{2,}\b", text.lower())
    stops = _stopwords()
    freq: dict[str, int] = {}
    for w in words:
        if w not in stops:
            freq[w] = freq.get(w, 0) + 1
    sorted_words = sorted(freq.items(), key=lambda x: -x[1])
    return [w for w, _ in sorted_words[:max_keywords]]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_keywords(
    text: str,
    *,
    max_keywords: int | None = None,
    use_cache: bool = True,
) -> list[str]:
    """Extract keywords from *text*, with layered caching.

    Returns a list of lowercase keyword strings.
    """
    n = max_keywords or int(os.environ.get("SHRAG_KEYWORD_MAX", "10"))
    key = _cache_key(text, n)

    if use_cache:
        cached = _l1_get(key) or _redis_get(key)
        if cached is not None:
            return cached

    # Try LLM first, then YAKE, then heuristic.
    keywords = _extract_llm(text, n)
    if not keywords:
        keywords = _extract_yake(text, n)
    if not keywords:
        keywords = _extract_tfidf_heuristic(text, n)

    if use_cache and keywords:
        _l1_put(key, keywords)
        _redis_put(key, keywords)

    return keywords


def extract_batch(
    texts: list[str],
    *,
    max_keywords: int | None = None,
) -> list[list[str]]:
    """Extract keywords for a list of texts."""
    return [extract_keywords(t, max_keywords=max_keywords) for t in texts]
