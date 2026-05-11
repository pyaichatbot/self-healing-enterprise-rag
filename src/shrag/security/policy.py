from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from shrag.observe.models import RequestContext, RetrievedChunk
from shrag.security.injection import has_injection_signal


@dataclass(slots=True)
class SecurityDecision:
    allowed: bool
    reasons: tuple[str, ...] = ()


class QueryPolicy(Protocol):
    def check_query(self, context: RequestContext) -> SecurityDecision: ...


class ChunkPolicy(Protocol):
    def check_chunks(self, context: RequestContext, chunks: Sequence[RetrievedChunk]) -> SecurityDecision: ...


class DefaultQueryPolicy:
    def check_query(self, context: RequestContext) -> SecurityDecision:
        flagged, signal = has_injection_signal(context.query)
        if flagged:
            return SecurityDecision(allowed=False, reasons=(f"injection:{signal}",))
        return SecurityDecision(allowed=True)


class DefaultChunkPolicy:
    def check_chunks(self, context: RequestContext, chunks: Sequence[RetrievedChunk]) -> SecurityDecision:
        _ = context
        blocked = [chunk.chunk_id for chunk in chunks if "forbidden" in chunk.text.lower()]
        if blocked:
            return SecurityDecision(allowed=False, reasons=tuple(f"blocked_chunk:{cid}" for cid in blocked))
        return SecurityDecision(allowed=True)


NoOpQueryPolicy = DefaultQueryPolicy
NoOpChunkPolicy = DefaultChunkPolicy
