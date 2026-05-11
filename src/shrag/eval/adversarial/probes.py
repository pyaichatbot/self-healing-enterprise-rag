from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from shrag.observe.models import GenerationResult, RequestContext, ScoreArtifact


@dataclass(slots=True)
class AdversarialProbeResult:
    findings: tuple[str, ...] = ()
    scores: tuple[ScoreArtifact, ...] = ()


class AdversarialProbe(Protocol):
    def run(self, context: RequestContext, generation: GenerationResult) -> AdversarialProbeResult: ...


class NoOpAdversarialProbe:
    def run(self, context: RequestContext, generation: GenerationResult) -> AdversarialProbeResult:
        _ = (context, generation)
        return AdversarialProbeResult()


def run_probes(
    context: RequestContext,
    generation: GenerationResult,
    probes: Sequence[AdversarialProbe],
) -> tuple[AdversarialProbeResult, ...]:
    return tuple(probe.run(context, generation) for probe in probes)
