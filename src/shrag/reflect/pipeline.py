from __future__ import annotations

from typing import Protocol, Sequence

from shrag.reflect.abstain import should_abstain
from shrag.reflect.calibration import calibrated_confidence
from shrag.reflect.cove import cove_questions
from shrag.reflect.critic import critique_response
from shrag.observe.models import GenerationResult, ReflectionOutcome, RequestContext, ScoreArtifact


class ReflectStage(Protocol):
    def reflect(
        self,
        context: RequestContext,
        generation: GenerationResult,
        signals: Sequence[ScoreArtifact] = (),
    ) -> ReflectionOutcome: ...


class BaselineReflectStage:
    """Deterministic baseline reflector with abstain/heal decisions."""

    def reflect(
        self,
        context: RequestContext,
        generation: GenerationResult,
        signals: Sequence[ScoreArtifact] = (),
    ) -> ReflectionOutcome:
        critic = critique_response(generation)
        combined = tuple(signals) + (critic,)
        abstain, abstain_reason = should_abstain(combined)
        confidence = calibrated_confidence(combined)
        issues: list[str] = []
        actions: list[str] = []
        if abstain:
            issues.append(abstain_reason)
            actions.append("abstain")
        if not critic.passed:
            issues.append(critic.reason or "critic_failed")
            actions.append("refine_answer")
        if confidence < 0.45:
            issues.append("low_confidence")
            actions.append("retrieve_more")
        if context.metadata.get("use_cove"):
            actions.extend(cove_questions(context.query))
        return ReflectionOutcome(
            should_heal=bool(actions),
            issues=tuple(issues),
            suggested_actions=tuple(actions),
            metadata={"confidence": confidence},
        )


NoOpReflectStage = BaselineReflectStage
