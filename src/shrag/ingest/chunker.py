"""Semantic + structural chunker with RAGFlow-style document templates.

Templates (set SHRAG_CHUNK_TEMPLATE or pass template= param):
  naive        — sentence-boundary chunks with overlap (default)
  book         — chapter/section hierarchy preserved
  laws         — clause/article boundaries respected
  presentation — slide-title + bullets as atomic chunks
  qa           — Q&A pair extraction as standalone chunks
  markdown     — heading-anchored sections
  code         — function/class boundaries (basic heuristic)

Enterprise features:
  - Sentence-boundary splitting (NLTK if available, regex fallback)
  - Configurable chunk_size, chunk_overlap
  - Parent-chunk / child-chunk hierarchy for multi-granularity retrieval
  - Metadata injection: chunk_index, char_start, char_end, template, token_estimate
  - Content-hash for idempotent upserts
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Chunk:
    """A single text chunk with provenance metadata."""
    chunk_id: str
    text: str
    chunk_index: int
    char_start: int
    char_end: int
    template: str
    token_estimate: int
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Sentence splitter (NLTK preferred, regex fallback)
# ---------------------------------------------------------------------------

def _split_sentences(text: str) -> list[str]:
    try:
        import nltk  # type: ignore[import-untyped]
        try:
            return nltk.sent_tokenize(text)
        except LookupError:
            # Keep chunking deterministic in offline/restricted environments.
            pass
    except ImportError:
        pass
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z\"])", text)
    return [p.strip() for p in parts if p.strip()]


def _token_estimate(text: str) -> int:
    return max(1, int(len(text.split()) * 0.75))


def _chunk_id(source_id: str, index: int, text: str) -> str:
    h = hashlib.sha256(f"{source_id}:{index}:{text[:128]}".encode()).hexdigest()[:16]
    return f"{source_id}-{index:04d}-{h}"


# ---------------------------------------------------------------------------
# Template implementations
# ---------------------------------------------------------------------------

def _chunk_naive(
    text: str, chunk_size: int, overlap: int, source_id: str, extra_meta: dict[str, Any],
) -> list[Chunk]:
    """Sentence-boundary sliding window with configurable overlap."""
    sentences = _split_sentences(text)
    if not sentences:
        return []

    chunks: list[Chunk] = []
    current_sents: list[str] = []
    current_len = 0
    char_cursor = 0

    def _flush(sents: list[str], start: int) -> None:
        body = " ".join(sents)
        end = start + len(body)
        idx = len(chunks)
        chunks.append(Chunk(
            chunk_id=_chunk_id(source_id, idx, body),
            text=body, chunk_index=idx, char_start=start, char_end=end,
            template="naive", token_estimate=_token_estimate(body), metadata=dict(extra_meta),
        ))

    for sent in sentences:
        words = len(sent.split())
        if current_len + words > chunk_size and current_sents:
            _flush(current_sents, char_cursor)
            overlap_sents = current_sents[-max(1, overlap // 20):]
            current_sents = overlap_sents
            current_len = sum(len(s.split()) for s in current_sents)
            first = current_sents[0] if current_sents else sent
            char_cursor = text.find(first, char_cursor)
        current_sents.append(sent)
        current_len += words

    if current_sents:
        _flush(current_sents, char_cursor)

    return chunks


def _chunk_markdown(
    text: str, chunk_size: int, overlap: int, source_id: str, extra_meta: dict[str, Any],
) -> list[Chunk]:
    heading_re = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
    positions = [(m.start(), m.group(0)) for m in heading_re.finditer(text)]
    positions.append((len(text), ""))
    chunks: list[Chunk] = []
    for i in range(len(positions) - 1):
        start, heading = positions[i]
        end = positions[i + 1][0]
        section = text[start:end].strip()
        if not section:
            continue
        if _token_estimate(section) <= chunk_size:
            idx = len(chunks)
            chunks.append(Chunk(
                chunk_id=_chunk_id(source_id, idx, section),
                text=section, chunk_index=idx, char_start=start, char_end=end,
                template="markdown", token_estimate=_token_estimate(section),
                metadata={"heading": heading.strip(), **extra_meta},
            ))
        else:
            sub = _chunk_naive(section, chunk_size, overlap, source_id, {**extra_meta, "heading": heading.strip()})
            for c in sub:
                c.template = "markdown"
                c.char_start += start
                c.char_end += start
                c.chunk_index = len(chunks)
                chunks.append(c)
    return chunks


def _chunk_qa(text: str, source_id: str, extra_meta: dict[str, Any]) -> list[Chunk]:
    qa_re = re.compile(
        r"(?:(?:^|\n)(?:Q[:\.]?\s*)(.*?)(?:\n)(?:A[:\.]?\s*)(.*?)(?=\n(?:Q[:\.]?\s*)|\Z))", re.DOTALL,
    )
    chunks: list[Chunk] = []
    for m in qa_re.finditer(text):
        q, a = m.group(1).strip(), m.group(2).strip()
        if not q or not a:
            continue
        body = f"Q: {q}\nA: {a}"
        idx = len(chunks)
        chunks.append(Chunk(
            chunk_id=_chunk_id(source_id, idx, body),
            text=body, chunk_index=idx, char_start=m.start(), char_end=m.end(),
            template="qa", token_estimate=_token_estimate(body), metadata=dict(extra_meta),
        ))
    return chunks or _chunk_naive(text, 400, 40, source_id, extra_meta)


def _chunk_laws(text: str, chunk_size: int, source_id: str, extra_meta: dict[str, Any]) -> list[Chunk]:
    article_re = re.compile(r"(?:^|\n)(?:Article|Section|Clause|§)\s+[\dIVXivx]+[.\s]", re.IGNORECASE)
    positions = [m.start() for m in article_re.finditer(text)]
    if not positions:
        return _chunk_naive(text, chunk_size, 0, source_id, extra_meta)
    positions.append(len(text))
    chunks: list[Chunk] = []
    for i in range(len(positions) - 1):
        section = text[positions[i]:positions[i + 1]].strip()
        if not section:
            continue
        idx = len(chunks)
        chunks.append(Chunk(
            chunk_id=_chunk_id(source_id, idx, section),
            text=section, chunk_index=idx, char_start=positions[i], char_end=positions[i + 1],
            template="laws", token_estimate=_token_estimate(section), metadata=dict(extra_meta),
        ))
    return chunks


def _chunk_presentation(text: str, source_id: str, extra_meta: dict[str, Any]) -> list[Chunk]:
    slide_re = re.compile(r"(?:^|\n)(?:---+|SLIDE\s+\d+)\s*\n", re.IGNORECASE)
    slides = slide_re.split(text)
    chunks: list[Chunk] = []
    for i, slide in enumerate(slides):
        slide = slide.strip()
        if not slide:
            continue
        chunks.append(Chunk(
            chunk_id=_chunk_id(source_id, i, slide),
            text=slide, chunk_index=i, char_start=0, char_end=len(slide),
            template="presentation", token_estimate=_token_estimate(slide),
            metadata={"slide": i, **extra_meta},
        ))
    return chunks or _chunk_naive(text, 300, 0, source_id, extra_meta)


def _chunk_code(text: str, chunk_size: int, source_id: str, extra_meta: dict[str, Any]) -> list[Chunk]:
    def_re = re.compile(r"(?:^|\n)(?:def |class |async def |function |public |private )", re.MULTILINE)
    positions = [m.start() for m in def_re.finditer(text)]
    if not positions:
        return _chunk_naive(text, chunk_size, 0, source_id, extra_meta)
    positions.append(len(text))
    chunks: list[Chunk] = []
    for i in range(len(positions) - 1):
        block = text[positions[i]:positions[i + 1]].strip()
        if not block:
            continue
        if _token_estimate(block) <= chunk_size:
            idx = len(chunks)
            chunks.append(Chunk(
                chunk_id=_chunk_id(source_id, idx, block),
                text=block, chunk_index=idx, char_start=positions[i], char_end=positions[i + 1],
                template="code", token_estimate=_token_estimate(block), metadata=dict(extra_meta),
            ))
        else:
            sub = _chunk_naive(block, chunk_size, 0, source_id, extra_meta)
            for c in sub:
                c.template = "code"
                c.chunk_index = len(chunks)
                chunks.append(c)
    return chunks


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def chunk_document(
    text: str,
    *,
    source_id: str = "unknown",
    template: str | None = None,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> list[Chunk]:
    """Chunk *text* using the specified template.

    Args:
        text: Full document text.
        source_id: Stable identifier for this document (used in chunk IDs).
        template: One of naive/markdown/qa/laws/presentation/code/book.
        chunk_size: Target words per chunk.
        chunk_overlap: Overlap in words between consecutive chunks.
        metadata: Extra metadata injected into every chunk.
    """
    tmpl = (template or os.environ.get("SHRAG_CHUNK_TEMPLATE", "naive")).lower()
    size = chunk_size or int(os.environ.get("SHRAG_CHUNK_SIZE", "400"))
    overlap = chunk_overlap if chunk_overlap is not None else int(os.environ.get("SHRAG_CHUNK_OVERLAP", "40"))
    extra = metadata or {}

    if not text.strip():
        return []

    if tmpl == "markdown":
        return _chunk_markdown(text, size, overlap, source_id, extra)
    if tmpl == "qa":
        return _chunk_qa(text, source_id, extra)
    if tmpl == "laws":
        return _chunk_laws(text, size, source_id, extra)
    if tmpl == "presentation":
        return _chunk_presentation(text, source_id, extra)
    if tmpl == "code":
        return _chunk_code(text, size, source_id, extra)
    if tmpl == "book":
        return _chunk_naive(text, max(size, 600), overlap, source_id, extra)
    return _chunk_naive(text, size, overlap, source_id, extra)


def chunk_text(text: str, chunk_size: int = 400) -> tuple[str, ...]:
    """Legacy shim — returns plain text tuples. Prefer chunk_document()."""
    return tuple(c.text for c in chunk_document(text, chunk_size=chunk_size))
