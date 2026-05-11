from __future__ import annotations


INJECTION_PATTERNS: tuple[str, ...] = (
    "ignore previous instructions",
    "system prompt",
    "reveal secrets",
    "bypass",
)


def detect_prompt_injection(text: str) -> tuple[bool, str]:
    lower = text.lower()
    for pattern in INJECTION_PATTERNS:
        if pattern in lower:
            return True, pattern
    return False, "none"
