from __future__ import annotations

from shrag.observe.models import GenerationResult, RequestContext, ScoreArtifact
from shrag.reflect.abstain import should_abstain
from shrag.reflect.calibration import calibrated_confidence
from shrag.reflect.cove import cove_questions, cove_verify
from shrag.reflect.critic import critique_response
from shrag.reflect.pipeline import BaselineReflectStage
from shrag.reflect.refine import refine_full


def test_should_abstain_reports_low_score_names():
    abstain, reason = should_abstain((ScoreArtifact(name="relevance", value=0.2), ScoreArtifact(name="crag", value=0.9)))
    assert abstain is True
    assert reason == "low_scores:relevance"


def test_calibrated_confidence_clamps_score_range():
    value = calibrated_confidence((ScoreArtifact(name="a", value=2.0), ScoreArtifact(name="b", value=-1.0)))
    assert value == 0.5


def test_reflect_stage_combines_actions_and_confidence(monkeypatch):
    monkeypatch.setattr("shrag.reflect.pipeline.critique_response", lambda generation: ScoreArtifact(name="critic", value=0.2, passed=False, reason="bad"))
    monkeypatch.setattr("shrag.reflect.pipeline.cove_questions", lambda query: ("verify 1", "verify 2"))

    stage = BaselineReflectStage()
    context = RequestContext(request_id="r1", query="complex", metadata={"use_cove": True})
    out = stage.reflect(context, GenerationResult(response_text="short"), signals=(ScoreArtifact(name="relevance", value=0.1),))

    assert out.should_heal is True
    assert "abstain" in out.suggested_actions
    assert "refine_answer" in out.suggested_actions
    assert "retrieve_more" in out.suggested_actions
    assert "verify 1" in out.suggested_actions
    assert out.metadata["confidence"] < 0.45


def test_cove_verify_falls_back_when_llm_unavailable(monkeypatch):
    monkeypatch.setattr("shrag.reflect.cove._answer_independently", lambda q: "this is not correct")
    monkeypatch.setattr("shrag.reflect.cove._check_consistency", lambda excerpt, independent: False)
    result = cove_verify("what is rollout", "Rollout is instant everywhere.", n_questions=2)

    assert len(result.questions) == 2
    assert result.overall_score == 0.0
    assert "Unverified claims detected" in result.revised_answer


def test_cove_questions_legacy_shim_returns_three_questions():
    qs = cove_questions("How does RAG work?")
    assert len(qs) == 3
    assert all(isinstance(q, str) for q in qs)


def test_refine_full_stops_when_score_meets_threshold(monkeypatch):
    monkeypatch.setattr("shrag.reflect.refine._score", lambda query, answer: 0.95)
    monkeypatch.setattr("shrag.reflect.refine._critique", lambda query, answer: "should not be used")
    result = refine_full("Initial answer", "q", max_rounds=3, quality_threshold=0.90)

    assert result.converged is True
    assert result.rounds_used == 1
    assert result.refined == "Initial answer."


def test_critique_response_reasoning_contract():
    weak = critique_response(GenerationResult(response_text="tiny"))
    strong = critique_response(GenerationResult(response_text="x" * 200))
    assert weak.passed is False
    assert weak.reason == "response_too_short"
    assert strong.passed is True
