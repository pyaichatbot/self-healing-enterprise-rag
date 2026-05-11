from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Mapping


@dataclass(slots=True)
class RequestContext:
    """Per-request context used across self-healing RAG stages."""

    request_id: str
    query: str
    user_id: str | None = None
    session_id: str | None = None
    trace_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass(slots=True)
class RetrievedChunk:
    """Canonical retrieval artifact consumed by grading and generation."""

    chunk_id: str
    source_id: str
    text: str
    score: float = 0.0
    rank: int = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ScoreArtifact:
    """Normalized score record shared by grading/evaluation/reflection."""

    name: str
    value: float
    reason: str | None = None
    passed: bool | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class GenerationResult:
    """Final text output plus provenance and score artifacts."""

    response_text: str
    citations: tuple[str, ...] = ()
    scores: tuple[ScoreArtifact, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ReflectionOutcome:
    """Reflection and healing recommendation artifact."""

    should_heal: bool
    issues: tuple[str, ...] = ()
    suggested_actions: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TraceRecord:
    """Normalized trace event emitted by API stage instrumentation."""

    trace_id: str
    request_id: str
    tenant_id: str
    user_id: str
    stage: str
    status: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    payload: Mapping[str, Any] = field(default_factory=dict)
