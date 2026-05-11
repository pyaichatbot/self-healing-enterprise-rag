from __future__ import annotations


def contradiction_score(answer: str, supporting: str, contradicting: str) -> float:
    """Simple contradiction heuristic for baseline adversarial checks.

    Returns 1.0 when answer aligns with supporting context and avoids contradicting terms,
    lower values otherwise.
    """

    answer_tokens = set(answer.lower().split())
    support_tokens = set(supporting.lower().split())
    contra_tokens = set(contradicting.lower().split())
    if not answer_tokens:
        return 0.0
    support_overlap = len(answer_tokens & support_tokens)
    contra_overlap = len(answer_tokens & contra_tokens)
    raw = (support_overlap - contra_overlap) / max(len(answer_tokens), 1)
    return max(0.0, min(1.0, raw + 0.5))
