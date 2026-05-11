from __future__ import annotations


JAILBREAK_TERMS: tuple[str, ...] = ("developer mode", "dan", "unfiltered", "policy override")


def detect_jailbreak_attempt(text: str) -> bool:
    lower = text.lower()
    return any(term in lower for term in JAILBREAK_TERMS)
