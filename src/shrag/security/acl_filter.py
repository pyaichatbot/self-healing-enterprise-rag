from __future__ import annotations

from collections.abc import Sequence

from shrag.observe.models import RetrievedChunk


def filter_chunks_by_acl(chunks: Sequence[RetrievedChunk], allowed_tenants: set[str]) -> tuple[RetrievedChunk, ...]:
    return tuple(
        chunk for chunk in chunks if str(chunk.metadata.get("tenant_id", "public")) in allowed_tenants or chunk.metadata.get("tenant_id") == "public"
    )
