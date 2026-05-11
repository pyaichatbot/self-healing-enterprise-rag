from __future__ import annotations


_BLOCK_TERMS: tuple[str, ...] = (
    "ignore previous instructions",
    "act as system",
    "override policy",
)


def has_injection_signal(query: str) -> tuple[bool, str]:
    lower = query.lower()
    for term in _BLOCK_TERMS:
        if term in lower:
            return True, term
    return False, "none"
