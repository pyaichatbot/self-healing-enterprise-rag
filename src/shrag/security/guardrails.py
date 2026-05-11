from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from shrag.observe.models import GenerationResult, RequestContext
from shrag.security.pii import redact_pii


@dataclass(slots=True)
class GuardrailResult:
    generation: GenerationResult
    redactions: tuple[str, ...] = ()


class OutputGuardrail(Protocol):
    def enforce(self, context: RequestContext, generation: GenerationResult) -> GuardrailResult: ...


class DefaultOutputGuardrail:
    def enforce(self, context: RequestContext, generation: GenerationResult) -> GuardrailResult:
        _ = context
        redacted = redact_pii(generation.response_text)
        if redacted == generation.response_text:
            return GuardrailResult(generation=generation)
        return GuardrailResult(
            generation=GenerationResult(
                response_text=redacted,
                citations=generation.citations,
                scores=generation.scores,
                metadata=generation.metadata,
            ),
            redactions=("email",),
        )


NoOpOutputGuardrail = DefaultOutputGuardrail
