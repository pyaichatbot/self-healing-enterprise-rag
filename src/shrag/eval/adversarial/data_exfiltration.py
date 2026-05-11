from __future__ import annotations

import re


_SECRET_RE = re.compile(r"(api[_-]?key|token|password|secret)", re.IGNORECASE)


def detect_exfiltration_intent(text: str) -> bool:
    return bool(_SECRET_RE.search(text))
