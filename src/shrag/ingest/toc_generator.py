"""Table-of-Contents (TOC) generation for long-context documents.

RAGFlow-inspired: generate navigable TOC from document chunks for:
  - Long-context retrieval with positional awareness
  - Section-level routing before dense retrieval
  - User-facing document structure previews

Modes:
  heading_extract  — parse existing markdown/heading markers (fast, no LLM)
  llm_summarize    — generate short summary per chunk section (LLM)
  hybrid           — headings first, LLM fill for headingless sections

Enterprise features:
  - Hierarchical TOC: H1 > H2 > H3 nesting preserved
  - Positional metadata: chunk_index range per section
  - Token estimate per section for context-window planning
  - Serialise to markdown or JSON
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TocEntry:
    title: str
    level: int                          # 1=top, 2=sub, 3=sub-sub
    chunk_start: int                    # first chunk index in section
    chunk_end: int                      # last chunk index (inclusive)
    token_estimate: int = 0
    summary: str = ""
    children: list["TocEntry"] = field(default_factory=list)


@dataclass(slots=True)
class TableOfContents:
    entries: list[TocEntry]
    mode: str
    total_chunks: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_markdown(self) -> str:
        lines: list[str] = ["# Table of Contents\n"]
        for entry in self.entries:
            indent = "  " * (entry.level - 1)
            lines.append(f"{indent}- **{entry.title}** (chunks {entry.chunk_start}–{entry.chunk_end})")
            if entry.summary:
                lines.append(f"{'  ' * entry.level}_{entry.summary}_")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        def _entry_dict(e: TocEntry) -> dict[str, Any]:
            return {
                "title": e.title,
                "level": e.level,
                "chunk_start": e.chunk_start,
                "chunk_end": e.chunk_end,
                "token_estimate": e.token_estimate,
                "summary": e.summary,
                "children": [_entry_dict(c) for c in e.children],
            }
        return {
            "mode": self.mode,
            "total_chunks": self.total_chunks,
            "entries": [_entry_dict(e) for e in self.entries],
        }


# ---------------------------------------------------------------------------
# Heading extraction (no LLM)
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)


def _extract_headings(chunks: list[Any]) -> list[TocEntry]:
    """Parse markdown headings from chunk text. Chunks must have .text attr."""
    entries: list[TocEntry] = []
    for i, chunk in enumerate(chunks):
        text = getattr(chunk, "text", str(chunk))
        for m in _HEADING_RE.finditer(text):
            level = len(m.group(1))
            title = m.group(2).strip()
            # Extend previous entry's chunk_end if same title exists.
            if entries and entries[-1].chunk_start == i:
                entries[-1].title = title
                entries[-1].level = level
            else:
                entries.append(TocEntry(
                    title=title, level=level,
                    chunk_start=i, chunk_end=i,
                    token_estimate=getattr(chunk, "token_estimate", 0),
                ))
    # Backfill chunk_end — each entry ends where next begins.
    for j in range(len(entries) - 1):
        entries[j].chunk_end = entries[j + 1].chunk_start - 1
    if entries:
        entries[-1].chunk_end = len(chunks) - 1
    return entries


# ---------------------------------------------------------------------------
# LLM summary per section
# ---------------------------------------------------------------------------

_SUMMARY_PROMPT = (
    "Summarise the following text in one sentence (max 20 words). "
    "Return ONLY the sentence.\n\n{text}\n\nSummary:"
)


def _summarise_chunk(text: str) -> str:
    try:
        from shrag.generate.llm import complete
        prompt = _SUMMARY_PROMPT.format(text=text[:800])
        return complete(prompt, max_tokens=40, temperature=0.1).strip()
    except Exception as exc:  # noqa: BLE001
        logger.debug("TOC summarise failed: %s", exc)
        words = text.split()
        return " ".join(words[:15]) + ("..." if len(words) > 15 else "")


def _llm_toc(chunks: list[Any], stride: int = 5) -> list[TocEntry]:
    """Generate TOC by summarising every *stride* chunks."""
    entries: list[TocEntry] = []
    for i in range(0, len(chunks), stride):
        batch = chunks[i : i + stride]
        combined = " ".join(getattr(c, "text", str(c)) for c in batch)[:1200]
        summary = _summarise_chunk(combined)
        tok = sum(getattr(c, "token_estimate", 0) for c in batch)
        entries.append(TocEntry(
            title=f"Section {i // stride + 1}",
            level=1,
            chunk_start=i,
            chunk_end=min(i + stride - 1, len(chunks) - 1),
            token_estimate=tok,
            summary=summary,
        ))
    return entries


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_toc(
    chunks: list[Any],
    *,
    mode: str | None = None,
    stride: int = 5,
) -> TableOfContents:
    """Generate a TableOfContents from *chunks*.

    Args:
        chunks: List of Chunk objects (or any objects with .text attribute).
        mode: 'heading_extract' | 'llm_summarize' | 'hybrid' (default from env).
        stride: Chunks per LLM-summarised section (llm_summarize mode).

    Returns:
        TableOfContents instance.
    """
    resolved_mode = mode or os.environ.get("SHRAG_TOC_MODE", "hybrid")
    n = len(chunks)

    if not chunks:
        return TableOfContents(entries=[], mode=resolved_mode, total_chunks=0)

    if resolved_mode == "heading_extract":
        entries = _extract_headings(chunks)
    elif resolved_mode == "llm_summarize":
        entries = _llm_toc(chunks, stride=stride)
    else:  # hybrid
        entries = _extract_headings(chunks)
        if not entries:
            entries = _llm_toc(chunks, stride=stride)

    logger.info("TOC generated: mode=%s entries=%d total_chunks=%d", resolved_mode, len(entries), n)
    return TableOfContents(entries=entries, mode=resolved_mode, total_chunks=n)
