from shrag.reflect import cove, refine


def test_cove_heuristic_questions_and_revision_note():
    questions = cove._heuristic_questions("What is X?", "Claim one. Claim two.", 3)
    revised = cove._revise_answer("Base answer", questions, [False, True, False])

    assert len(questions) == 3
    assert "[cove] Unverified claims" in revised


def test_cove_check_consistency_fallback_negation():
    assert cove._check_consistency("claim", "this is correct") is True
    original_import = __import__

    def _fail_import(name, *args, **kwargs):
        if name == "shrag.generate.llm":
            raise ImportError("forced fallback")
        return original_import(name, *args, **kwargs)

    import builtins

    try:
        builtins.__import__ = _fail_import
        assert cove._check_consistency("claim", "this is incorrect") is False
    finally:
        builtins.__import__ = original_import


def test_cove_verify_end_to_end_with_stubbed_internal_functions(monkeypatch):
    monkeypatch.setattr(cove, "_generate_questions", lambda query, answer, n: ["Q1?", "Q2?"])
    monkeypatch.setattr(cove, "_answer_independently", lambda question: "answer")
    monkeypatch.setattr(cove, "_check_consistency", lambda excerpt, independent: excerpt.startswith("A"))

    result = cove.cove_verify("query", "A one. B two.", n_questions=2)

    assert result.questions == ["Q1?", "Q2?"]
    assert result.confirmed == [True, False]
    assert 0.0 <= result.overall_score <= 1.0


def test_refine_full_early_converges_when_quality_high(monkeypatch):
    monkeypatch.setattr(refine, "_score", lambda query, answer: 0.95)

    result = refine.refine_full("Base answer", "query", max_rounds=3, quality_threshold=0.85)

    assert result.converged is True
    assert result.rounds_used == 1


def test_refine_full_stops_when_lgtm(monkeypatch):
    scores = iter([0.2, 0.2])
    monkeypatch.setattr(refine, "_score", lambda query, answer: next(scores))
    monkeypatch.setattr(refine, "_critique", lambda query, answer: "LGTM")

    result = refine.refine_full("Answer", "query", max_rounds=2, quality_threshold=0.9)

    assert result.converged is True
    assert result.critiques == ["LGTM"]


def test_refine_full_similarity_convergence(monkeypatch):
    scores = iter([0.1, 0.1])
    monkeypatch.setattr(refine, "_score", lambda query, answer: next(scores))
    monkeypatch.setattr(refine, "_critique", lambda query, answer: "needs polish")
    monkeypatch.setattr(refine, "_improve", lambda answer, critique: answer + " ")

    result = refine.refine_full("unchanged words", "query", max_rounds=2, quality_threshold=0.9)

    assert result.converged is True


def test_refine_answer_returns_refined_string(monkeypatch):
    monkeypatch.setattr(refine, "refine_full", lambda *args, **kwargs: refine.RefineResult(
        original="o", refined="r", rounds_used=1, converged=True
    ))
    assert refine.refine_answer("x", "q") == "r"
