from __future__ import annotations

from typing import Protocol, Sequence

from shrag.generate.citations import extract_citations
from shrag.generate.llm import complete
from shrag.generate.prompts import build_prompt
from shrag.observe.models import GenerationResult, RequestContext, RetrievedChunk
from shrag.settings import settings


class GenerateStage(Protocol):
    def generate(self, context: RequestContext, chunks: Sequence[RetrievedChunk]) -> GenerationResult: ...


class BaselineGenerateStage:
    """Generation stage with provider-backed completion and citation extraction."""

    def generate(self, context: RequestContext, chunks: Sequence[RetrievedChunk]) -> GenerationResult:
        if settings.generate_require_evidence and not chunks:
            return GenerationResult(response_text="Insufficient evidence.", citations=())
        prompt = build_prompt(context.query, chunks)
        answer = complete(prompt, system=settings.generate_system_prompt)
        citations = extract_citations(answer, chunks)
        return GenerationResult(response_text=answer, citations=citations)


NoOpGenerateStage = BaselineGenerateStage
