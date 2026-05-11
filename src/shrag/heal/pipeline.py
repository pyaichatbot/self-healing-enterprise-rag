from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from shrag.heal.canary import canary_enabled
from shrag.heal.circuit import circuit_breaker
from shrag.heal.repair import repair_response
from shrag.heal.retry import retry_budget
from shrag.observe.models import GenerationResult, ReflectionOutcome, RequestContext
from shrag.reflect.refine import refine_answer


@dataclass(slots=True)
class HealResult:
    generation: GenerationResult
    applied_actions: tuple[str, ...] = ()


class HealStage(Protocol):
    def heal(
        self,
        context: RequestContext,
        generation: GenerationResult,
        reflection: ReflectionOutcome,
    ) -> HealResult: ...


class BaselineHealStage:
    """Deterministic baseline healer with circuit/retry/refine hooks."""

    def heal(
        self,
        context: RequestContext,
        generation: GenerationResult,
        reflection: ReflectionOutcome,
    ) -> HealResult:
        decision = circuit_breaker(error_rate=0.3 if reflection.issues else 0.0)
        if decision.open:
            repair = repair_response(generation, "healing_circuit_open")
            return HealResult(
                generation=repair.generation,
                applied_actions=("circuit_open",),
            )

        actions: list[str] = []
        healed = generation
        if retry_budget(0):
            if "refine_answer" in reflection.suggested_actions or canary_enabled(context.request_id, ratio=0.2):
                healed = GenerationResult(
                    response_text=refine_answer(healed.response_text),
                    citations=healed.citations,
                    scores=healed.scores,
                    metadata=healed.metadata,
                )
                actions.append("refined")
        if reflection.issues:
            repair = repair_response(healed, ",".join(reflection.issues))
            healed = repair.generation
            actions.append("repaired")
        return HealResult(generation=healed, applied_actions=tuple(actions))


NoOpHealStage = BaselineHealStage
