from __future__ import annotations

from shrag.security.pii import redact_pii


def scrub(text: str) -> str:
    return redact_pii(text)
