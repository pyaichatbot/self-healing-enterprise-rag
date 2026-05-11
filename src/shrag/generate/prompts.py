from __future__ import annotations

from collections.abc import Sequence

from shrag.observe.models import RetrievedChunk


def build_prompt(query: str, chunks: Sequence[RetrievedChunk]) -> str:
    context = "\n".join(f"[{c.source_id}] {c.text}" for c in chunks[:5])
    return f"Answer the query using provided context only.\\nQuery: {query}\\nContext:\\n{context}"
