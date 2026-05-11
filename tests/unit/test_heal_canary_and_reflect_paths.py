from shrag.heal import canary
from shrag.reflect import cove, refine


def test_canary_enabled_stable():
    assert canary.canary_enabled("req-1", ratio=1.0) is True
    assert canary.canary_enabled("req-1", ratio=0.0) is False


def test_canary_stats_after_shadow():
    canary.run_canary_shadow("req-shadow", 0.5, lambda: 0.6, variant="v1", alert_threshold=-1.0)
    # allow thread to run
    import time
    time.sleep(0.05)
    stats = canary.get_canary_stats(last_n=10)
    assert "count" in stats


def test_refine_full_converges_with_high_score(monkeypatch):
    monkeypatch.setattr(refine, "_score", lambda query, answer: 0.99)
    out = refine.refine_full("answer", "query", max_rounds=2, quality_threshold=0.8)
    assert out.converged is True


def test_cove_verify_basic(monkeypatch):
    monkeypatch.setattr(cove, "_generate_questions", lambda q, a, n: ["Q1?"])
    monkeypatch.setattr(cove, "_answer_independently", lambda q: "Yes")
    monkeypatch.setattr(cove, "_check_consistency", lambda orig, indep: True)
    out = cove.cove_verify("query", "answer")
    assert out.overall_score == 1.0

