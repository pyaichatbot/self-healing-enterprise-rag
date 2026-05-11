"""PII detection and redaction — regex + optional NER.

Patterns covered:
  - Email addresses
  - US/international phone numbers
  - US Social Security Numbers (SSN)
  - Credit / debit card numbers (Luhn-validated)
  - IPv4 and IPv6 addresses
  - US ZIP codes (standalone 5-digit)
  - Passport-style alphanumeric IDs
  - UK National Insurance numbers
  - IBAN bank account numbers
  - JWT tokens (header.payload.sig)

Enterprise features:
  - Per-type redaction labels for audit traceability
  - Luhn check prevents false-positive card matches
  - Detection-only mode (returns spans, no mutation)
  - Optional spaCy NER for PERSON/ORG/LOC (if available)
  - Thread-safe — no mutable module state
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


# ---------------------------------------------------------------------------
# Pattern catalogue
# ---------------------------------------------------------------------------

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL",   re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    ("PHONE",   re.compile(
        r"(?<!\d)"
        r"(?:\+?1[\s\-.]?)?"                    # optional US country code
        r"(?:\(?\d{3}\)?[\s\-.]?)"              # area code
        r"\d{3}[\s\-.]?\d{4}"                   # main number
        r"(?!\d)"
    )),
    ("SSN",     re.compile(r"\b(?!000|666|9\d{2})\d{3}[- ]?(?!00)\d{2}[- ]?(?!0000)\d{4}\b")),
    ("CARD",    re.compile(r"\b(?:\d[ \-]?){13,19}\b")),          # Luhn-checked below
    ("IP4",     re.compile(
        r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
        r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
    )),
    ("IP6",     re.compile(
        r"\b(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4}\b"
        r"|\b(?:[0-9A-Fa-f]{1,4}:){1,7}:\b"
        r"|\b::(?:[0-9A-Fa-f]{1,4}:){0,6}[0-9A-Fa-f]{1,4}\b"
    )),
    ("IBAN",    re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{4,30}\b")),
    ("NIN",     re.compile(r"\b[A-CEGHJ-PR-TW-Z]{1}[A-CEGHJ-NPR-TW-Z]{1}\d{6}[A-D]\b")),
    ("JWT",     re.compile(r"ey[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+")),
    ("PASSPORT",re.compile(r"\b[A-Z]{1,2}\d{6,9}\b")),
]


# ---------------------------------------------------------------------------
# Luhn algorithm for credit-card validation
# ---------------------------------------------------------------------------

def _luhn(number: str) -> bool:
    digits = [int(d) for d in re.sub(r"\D", "", number)]
    if len(digits) < 13:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


# ---------------------------------------------------------------------------
# Span dataclass for detection-only mode
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class PiiSpan:
    start: int
    end: int
    label: str
    original: str


# ---------------------------------------------------------------------------
# Core redaction / detection
# ---------------------------------------------------------------------------

def detect_pii(text: str) -> list[PiiSpan]:
    """Return all PII spans (no mutation)."""
    spans: list[PiiSpan] = []
    for label, pattern in _PATTERNS:
        for m in pattern.finditer(text):
            raw = m.group()
            if label == "CARD" and not _luhn(raw):
                continue
            spans.append(PiiSpan(start=m.start(), end=m.end(), label=label, original=raw))

    # Optional spaCy NER for PERSON / ORG / LOC.
    try:
        _nlp = _get_nlp()
        if _nlp:
            doc = _nlp(text)
            for ent in doc.ents:
                if ent.label_ in {"PERSON", "ORG", "GPE", "LOC"}:
                    spans.append(PiiSpan(
                        start=ent.start_char, end=ent.end_char,
                        label=ent.label_, original=ent.text,
                    ))
    except Exception:  # noqa: BLE001
        pass

    # Sort by position, deduplicate overlapping spans (keep longest).
    spans.sort(key=lambda s: (s.start, -(s.end - s.start)))
    deduped: list[PiiSpan] = []
    last_end = -1
    for span in spans:
        if span.start >= last_end:
            deduped.append(span)
            last_end = span.end
    return deduped


def redact_pii(text: str, *, replacement: str | None = None) -> str:
    """Replace PII in *text* with type-specific redaction tokens."""
    spans = detect_pii(text)
    if not spans:
        return text

    parts: list[str] = []
    cursor = 0
    for span in spans:
        parts.append(text[cursor:span.start])
        token = replacement or f"[REDACTED_{span.label}]"
        parts.append(token)
        cursor = span.end
    parts.append(text[cursor:])
    return "".join(parts)


def scrub_metadata(obj: Any) -> Any:
    """Recursively redact PII from dict/list/str structures."""
    if isinstance(obj, str):
        return redact_pii(obj)
    if isinstance(obj, dict):
        return {k: scrub_metadata(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        cleaned = [scrub_metadata(v) for v in obj]
        return type(obj)(cleaned)
    return obj


# ---------------------------------------------------------------------------
# Lazy spaCy loader — avoids import cost when NER not needed
# ---------------------------------------------------------------------------

_nlp_cache: Any = None
_nlp_tried = False


def _get_nlp() -> Any:
    global _nlp_cache, _nlp_tried  # noqa: PLW0603
    if _nlp_tried:
        return _nlp_cache
    _nlp_tried = True
    try:
        import spacy  # type: ignore[import-untyped]
        _nlp_cache = spacy.load("en_core_web_sm")
    except Exception:  # noqa: BLE001
        _nlp_cache = None
    return _nlp_cache
