"""Chain-of-Verification (CoVe) — factual consistency checking.

Algorithm (Dhuliawala et al. 2023 — adapted):
  1. Generate verification questions from the answer
  2. Answer each question independently (no original answer in context)
  3. Compare independent answers against original answer
  4. Score: fraction of questions confirmed by independent answers
  5. Return revised answer with low-confidence claims flagged

Enterprise features:
  - LLM-backed question generation (degrades to heuristic on failure)
  - Independent answer generation per question
  - Confidence score per question (binary confirmed / unconfirmed)
  - Revised answer appends unconfirmed-claim warnings inline
  - Configurable max questions (SHRAG_COVE_MAX_QUESTIONS)
  - Full result dataclass for downstream grading integration
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class VerificationResult:
    questions: list[str]
    independent_answers: list[str]
    confirmed: list[bool]
    overall_score: float          # fraction confirmed (0.0–1.0)
    revised_answer: str
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Question generation
# ---------------------------------------------------------------------------

_QUESTION_GEN_PROMPT = (
    "Given the following question and answer, generate {n} short, specific "
    "yes/no or fact-check questions that verify the factual claims in the answer. "
    "Return each question on its own line, no numbering.\n\n"
    "Original question: {query}\n\nAnswer:\n{answer}\n\nVerification questions:"
)


def _generate_questions(query: str, answer: str, n: int) -> list[str]:
    """Use LLM to generate verification questions. Heuristic fallback."""
    try:
        from shrag.generate.llm import complete
        prompt = _QUESTION_GEN_PROMPT.format(n=n, query=query, answer=answer)
        raw = complete(prompt, max_tokens=n * 30, temperature=0.1)
        lines = [ln.strip().lstrip("-•*0123456789.)").strip() for ln in raw.splitlines() if ln.strip()]
        lines = [ln for ln in lines if len(ln) > 10 and "?" in ln]
        return lines[:n] if lines else _heuristic_questions(query, answer, n)
    except Exception as exc:  # noqa: BLE001
        logger.debug("CoVe question gen failed: %s", exc)
        return _heuristic_questions(query, answer, n)


def _heuristic_questions(query: str, answer: str, n: int) -> list[str]:
    """Extract noun phrases as fact-check questions."""
    sentences = re.split(r"(?<=[.!?])\s+", answer.strip())
    questions: list[str] = [
        f"What evidence directly supports: {query}?",
        "Which claim in this answer is least certain?",
        "What source would falsify the main claim?",
    ]
    for sent in sentences[:n]:
        sent = sent.strip()
        if len(sent) > 20:
            questions.append(f"Is the following accurate: {sent[:120]}")
    return questions[:n]


# ---------------------------------------------------------------------------
# Independent answering
# ---------------------------------------------------------------------------

_INDEPENDENT_PROMPT = (
    "Answer the following question as concisely as possible, using only "
    "your general knowledge. Do NOT look at any prior answer.\n\n"
    "Question: {question}\n\nAnswer:"
)


def _answer_independently(question: str) -> str:
    """Answer a verification question without the original answer in context."""
    try:
        from shrag.generate.llm import complete
        prompt = _INDEPENDENT_PROMPT.format(question=question)
        return complete(prompt, max_tokens=80, temperature=0.1)
    except Exception as exc:  # noqa: BLE001
        logger.debug("CoVe independent answer failed: %s", exc)
        return ""


# ---------------------------------------------------------------------------
# Consistency check
# ---------------------------------------------------------------------------

_CONSISTENCY_PROMPT = (
    "Does the following independent answer confirm or contradict the original answer? "
    "Reply with exactly one word: CONFIRMED or UNCONFIRMED.\n\n"
    "Original answer excerpt: {original_excerpt}\n\n"
    "Independent answer: {independent}\n\nVerdict:"
)

_NEGATIVE_MARKERS = re.compile(
    r"\b(no|not|incorrect|false|unconfirmed|contradict|disagree|wrong|inaccurate)\b",
    re.IGNORECASE,
)


def _check_consistency(original_excerpt: str, independent: str) -> bool:
    """Return True if independent answer confirms the original claim."""
    if not independent.strip():
        return False
    try:
        from shrag.generate.llm import complete
        prompt = _CONSISTENCY_PROMPT.format(
            original_excerpt=original_excerpt[:200],
            independent=independent[:200],
        )
        verdict = complete(prompt, max_tokens=5, temperature=0.0).strip().upper()
        return "CONFIRMED" in verdict
    except Exception:  # noqa: BLE001
        pass
    # Heuristic fallback: flag if independent answer contains strong negations.
    return not bool(_NEGATIVE_MARKERS.search(independent))


# ---------------------------------------------------------------------------
# Answer revision
# ---------------------------------------------------------------------------

def _revise_answer(answer: str, questions: list[str], confirmed: list[bool]) -> str:
    """Annotate answer with unconfirmed-claim warnings."""
    unconfirmed = [q for q, c in zip(questions, confirmed) if not c]
    if not unconfirmed:
        return answer
    warnings = "; ".join(f'"{q}"' for q in unconfirmed[:3])
    note = f"\n\n⚠ [cove] Unverified claims detected — {warnings}"
    return answer + note


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def cove_verify(
    query: str,
    answer: str,
    *,
    n_questions: int | None = None,
) -> VerificationResult:
    """Run Chain-of-Verification on *answer* w.r.t. *query*.

    Returns a VerificationResult with score and optionally revised answer.
    """
    n = n_questions or int(os.environ.get("SHRAG_COVE_MAX_QUESTIONS", "4"))

    questions = _generate_questions(query, answer, n)
    independent_answers: list[str] = []
    confirmed: list[bool] = []

    # Extract short answer excerpts for consistency comparison.
    answer_sentences = re.split(r"(?<=[.!?])\s+", answer.strip())

    for i, question in enumerate(questions):
        ind_ans = _answer_independently(question)
        independent_answers.append(ind_ans)
        excerpt = answer_sentences[min(i, len(answer_sentences) - 1)] if answer_sentences else answer[:200]
        confirmed.append(_check_consistency(excerpt, ind_ans))

    score = sum(confirmed) / len(confirmed) if confirmed else 1.0
    revised = _revise_answer(answer, questions, confirmed)

    logger.info(
        "CoVe score=%.2f confirmed=%d/%d for query=%r",
        score, sum(confirmed), len(confirmed), query[:60],
    )

    return VerificationResult(
        questions=questions,
        independent_answers=independent_answers,
        confirmed=confirmed,
        overall_score=score,
        revised_answer=revised,
        metadata={"n_questions": len(questions), "query_snippet": query[:80]},
    )


def cove_questions(query: str) -> tuple[str, ...]:
    """Legacy shim — returns heuristic verification questions."""
    return tuple(_heuristic_questions(query, "", 3))
