from __future__ import annotations

from shrag.observe.models import GenerationResult, ScoreArtifact


def critique_response(generation: GenerationResult) -> ScoreArtifact:
    text = generation.response_text.strip()
    value = min(len(text) / 400.0, 1.0)
    passed = len(text) >= 80
    reason = "response_too_short" if not passed else "sufficient_detail"
    return ScoreArtifact(name="critic", value=value, passed=passed, reason=reason)
