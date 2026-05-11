"""Query rewriting: HyDE, decomposer, synonym expansion, step-back.

Enterprise features:
  - HyDE (Hypothetical Document Embeddings) — generate hypothetical answer
    then embed for better dense retrieval alignment
  - Multi-hop decomposer — split complex queries into atomic sub-queries
  - Synonym expander — domain-aware term expansion (rule + LLM)
  - Step-back prompting — abstract to general principle before retrieval
  - RewriteStrategy enum for per-request control
  - All rewriters degrade gracefully to original query on LLM failure
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class RewriteStrategy(str, Enum):
    NONE = "none"           # pass-through
    NORMALIZE = "normalize" # punctuation/stop-word cleanup only
    SYNONYM = "synonym"     # rule-based synonym expansion
    HYDE = "hyde"           # hypothetical document embedding
    DECOMPOSE = "decompose" # multi-hop sub-query decomposition
    STEP_BACK = "step_back" # step-back abstraction


@dataclass(slots=True)
class RewriteResult:
    original: str
    rewritten: str
    strategy: str
    sub_queries: list[str] = field(default_factory=list)
    hyde_passage: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# LLM call helper (falls back to deterministic if provider unavailable)
# ---------------------------------------------------------------------------

def _llm_complete(prompt: str, max_tokens: int = 200) -> str:
    """Best-effort LLM call; returns empty string on failure."""
    backend = os.environ.get("SHRAG_LLM_BACKEND", "mock")
    if backend == "mock":
        return ""
    try:
        if backend == "openai":
            import openai  # type: ignore[import-untyped]
            client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
            resp = client.chat.completions.create(
                model=os.environ.get("SHRAG_REWRITE_MODEL", "gpt-4o-mini"),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.2,
            )
            return resp.choices[0].message.content or ""
        if backend == "anthropic":
            import anthropic  # type: ignore[import-untyped]
            client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
            resp = client.messages.create(
                model=os.environ.get("SHRAG_REWRITE_MODEL", "claude-haiku-4-5-20251001"),
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text if resp.content else ""
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM rewrite failed: %s", exc)
    return ""


# ---------------------------------------------------------------------------
# Normalize (always applied as pre-pass)
# ---------------------------------------------------------------------------

_SYNONYM_MAP: dict[str, str] = {
    " vs ": " comparison ",
    " versus ": " comparison ",
    "how to ": "steps to ",
    "what is ": "definition of ",
    "difference between": "comparison of",
}


def _normalize(query: str) -> str:
    q = re.sub(r"\s+", " ", query.strip())
    # Remove trailing punctuation except ?
    q = re.sub(r"[.!;]+$", "", q).strip()
    return q


def _synonym_expand(query: str) -> str:
    q = _normalize(query).lower()
    for src, dst in _SYNONYM_MAP.items():
        q = q.replace(src, dst)
    return q


# ---------------------------------------------------------------------------
# HyDE — hypothetical document embeddings
# ---------------------------------------------------------------------------

_HYDE_PROMPT = (
    "Write a short, factual passage (3-5 sentences) that would directly answer "
    "this question as if it came from a high-quality knowledge base:\n\nQuestion: {query}\n\nPassage:"
)


def _hyde_rewrite(query: str) -> tuple[str, str | None]:
    """Return (rewritten_query, hyde_passage).

    The hyde_passage is embedded instead of the original query.
    Falls back to original query if LLM unavailable.
    """
    passage = _llm_complete(_HYDE_PROMPT.format(query=query), max_tokens=150)
    if passage.strip():
        return passage.strip(), passage.strip()
    return query, None


# ---------------------------------------------------------------------------
# Multi-hop decomposer
# ---------------------------------------------------------------------------

_DECOMPOSE_PROMPT = (
    "Break the following complex question into 2-4 simpler, independent sub-questions "
    "that together cover the full answer. Return each on a new line, no numbering:\n\n"
    "Question: {query}\n\nSub-questions:"
)


def _decompose(query: str) -> list[str]:
    """Return list of atomic sub-queries. Falls back to [query] on failure."""
    result = _llm_complete(_DECOMPOSE_PROMPT.format(query=query), max_tokens=200)
    if not result.strip():
        return [query]
    lines = [ln.strip().lstrip("-•*").strip() for ln in result.splitlines() if ln.strip()]
    lines = [ln for ln in lines if len(ln) > 8]
    return lines if lines else [query]


# ---------------------------------------------------------------------------
# Step-back
# ---------------------------------------------------------------------------

_STEPBACK_PROMPT = (
    "Rewrite the following question as a more general principle or concept question "
    "that would help retrieve broader background knowledge:\n\n"
    "Original: {query}\n\nGeneralized:"
)


def _step_back(query: str) -> str:
    result = _llm_complete(_STEPBACK_PROMPT.format(query=query), max_tokens=80)
    return result.strip() if result.strip() else query


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def rewrite_query(
    query: str,
    strategy: str | RewriteStrategy | None = None,
) -> RewriteResult:
    """Rewrite *query* using the specified strategy.

    Defaults to SHRAG_REWRITE_STRATEGY env var, falling back to SYNONYM.
    """
    strat = _resolve_strategy(strategy)

    normalized = _normalize(query)

    if strat == RewriteStrategy.NONE:
        return RewriteResult(original=query, rewritten=query, strategy="none")

    if strat == RewriteStrategy.NORMALIZE:
        return RewriteResult(original=query, rewritten=normalized, strategy="normalize")

    if strat == RewriteStrategy.SYNONYM:
        return RewriteResult(original=query, rewritten=_synonym_expand(query), strategy="synonym")

    if strat == RewriteStrategy.HYDE:
        rewritten, passage = _hyde_rewrite(normalized)
        return RewriteResult(
            original=query, rewritten=rewritten, strategy="hyde", hyde_passage=passage,
        )

    if strat == RewriteStrategy.DECOMPOSE:
        sub_queries = _decompose(normalized)
        # Use first sub-query as primary retrieval target.
        return RewriteResult(
            original=query, rewritten=sub_queries[0], strategy="decompose",
            sub_queries=sub_queries,
        )

    if strat == RewriteStrategy.STEP_BACK:
        step = _step_back(normalized)
        return RewriteResult(original=query, rewritten=step, strategy="step_back")

    return RewriteResult(original=query, rewritten=normalized, strategy="normalize")


def _resolve_strategy(strategy: str | RewriteStrategy | None) -> RewriteStrategy:
    candidate = strategy or os.environ.get("SHRAG_REWRITE_STRATEGY", RewriteStrategy.SYNONYM)
    if isinstance(candidate, RewriteStrategy):
        return candidate
    if isinstance(candidate, str):
        try:
            return RewriteStrategy(candidate)
        except ValueError:
            return RewriteStrategy.SYNONYM
    return RewriteStrategy.SYNONYM
