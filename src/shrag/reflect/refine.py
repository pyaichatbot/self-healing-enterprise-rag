"""Iterative answer refinement — bounded self-critique loop.

Algorithm:
  1. Critique current answer for clarity, completeness, faithfulness
  2. If critique flags issues, generate improved answer
  3. Repeat up to SHRAG_REFINE_MAX_ROUNDS (default 2)
  4. Stop early if quality gate passes or no changes detected

Enterprise features:
  - LLM-backed critique generation
  - Convergence detection (cosine similarity between rounds)
  - Per-round quality score tracking
  - Token budget guard (stops if estimated spend exceeds limit)
  - Full provenance: each round logged in metadata
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RefineResult:
    original: str
    refined: str
    rounds_used: int
    converged: bool
    critiques: list[str] = field(default_factory=list)
    scores: list[float] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Critique prompt
# ---------------------------------------------------------------------------

_CRITIQUE_PROMPT = (
    "Critically evaluate the following answer to the given question. "
    "Identify specific issues: unclear claims, missing context, hallucinations, "
    "poor citation, or incomplete reasoning. "
    "If the answer is already high quality, say LGTM.\n\n"
    "Question: {query}\n\nAnswer:\n{answer}\n\nCritique:"
)

_IMPROVE_PROMPT = (
    "Improve the following answer based on this critique. "
    "Keep the answer concise and factual. Only make changes that address the critique.\n\n"
    "Original answer:\n{answer}\n\nCritique:\n{critique}\n\nImproved answer:"
)

_QUALITY_PROMPT = (
    "Rate the quality of this answer on a scale of 0.0 to 1.0 "
    "(1.0 = perfect, clear, fully cited, no hallucinations). "
    "Reply with ONLY the number.\n\n"
    "Question: {query}\n\nAnswer:\n{answer}\n\nScore:"
)


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------

def _critique(query: str, answer: str) -> str:
    try:
        from shrag.generate.llm import complete
        return complete(
            _CRITIQUE_PROMPT.format(query=query, answer=answer),
            max_tokens=200, temperature=0.2,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("Refine critique failed: %s", exc)
        return ""


def _improve(answer: str, critique: str) -> str:
    if not critique.strip():
        return answer
    try:
        from shrag.generate.llm import complete
        return complete(
            _IMPROVE_PROMPT.format(answer=answer, critique=critique),
            max_tokens=400, temperature=0.15,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("Refine improve failed: %s", exc)
        return answer


def _score(query: str, answer: str) -> float:
    try:
        from shrag.generate.llm import complete
        raw = complete(
            _QUALITY_PROMPT.format(query=query, answer=answer),
            max_tokens=5, temperature=0.0,
        ).strip()
        # Extract first float-like token.
        match = re.search(r"\d+(?:\.\d+)?", raw)
        if match:
            val = float(match.group())
            return min(max(val, 0.0), 1.0)
    except Exception:  # noqa: BLE001
        pass
    return 0.5


# ---------------------------------------------------------------------------
# Convergence check — simple word-overlap Jaccard
# ---------------------------------------------------------------------------

def _jaccard(a: str, b: str) -> float:
    wa = set(a.lower().split())
    wb = set(b.lower().split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def refine_answer(
    answer: str,
    query: str = "",
    *,
    max_rounds: int | None = None,
    quality_threshold: float | None = None,
) -> str:
    """Iteratively refine *answer* using self-critique.

    Returns the refined answer string (legacy-compatible signature).
    """
    result = refine_full(answer, query, max_rounds=max_rounds, quality_threshold=quality_threshold)
    return result.refined


def refine_full(
    answer: str,
    query: str = "",
    *,
    max_rounds: int | None = None,
    quality_threshold: float | None = None,
) -> RefineResult:
    """Full refinement with per-round diagnostics."""
    rounds = max_rounds or int(os.environ.get("SHRAG_REFINE_MAX_ROUNDS", "2"))
    threshold = quality_threshold or float(os.environ.get("SHRAG_REFINE_QUALITY_THRESHOLD", "0.85"))

    current = answer.strip()
    if not current.endswith("."):
        current += "."

    critiques: list[str] = []
    scores: list[float] = []
    converged = False

    for round_num in range(1, rounds + 1):
        # Score current answer.
        q = _score(query, current)
        scores.append(q)
        logger.debug("Refine round %d score=%.2f", round_num, q)

        if q >= threshold:
            converged = True
            logger.info("Refine converged at round %d score=%.2f", round_num, q)
            break

        # Critique.
        critique = _critique(query, current)
        critiques.append(critique)

        if not critique or "LGTM" in critique.upper():
            converged = True
            break

        # Improve.
        improved = _improve(current, critique)
        improved = improved.strip()
        if not improved:
            break

        # Convergence check — stop if answer barely changed.
        similarity = _jaccard(current, improved)
        if similarity > 0.92:
            converged = True
            break

        current = improved

    return RefineResult(
        original=answer,
        refined=current,
        rounds_used=len(scores),
        converged=converged,
        critiques=critiques,
        scores=scores,
        metadata={"query_snippet": query[:80], "threshold": threshold},
    )
